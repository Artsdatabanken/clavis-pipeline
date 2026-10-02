#!/usr/bin/env python3
"""Refine a Clavis JSON file: pure Clavis→Clavis transformations, no
source material required.

Pass 1 (implemented): merge characters with identical titles.
  - Categorical groups: states with the same label collapse; states with
    distinct labels are unioned under the canonical character.
  - Quantitative groups: parse each state's numeric range, take the
    union of breakpoints across all chars in the group, build atomic
    bins between consecutive breakpoints, and re-encode each original
    state's assertions as paired 0.5s on the atomic bins it covers.
    Worst case (every original endpoint distinct) is one atomic bin
    per source-mentioned integer; a later coarsening step can bin those
    into discriminating ranges.

Statements are re-pointed and re-emitted so the frequency rule still
holds (confident → one 1, uncertain → 0.5 each).

Future passes (not yet implemented):
  - Synonymous-state merge ("pale yellow" / "yellowish-white")
  - Bundled-state split ("red, sometimes white")
  - Hierarchy inference (genus/family from binomial scientific names)
  - Statement hoisting (shared assertions move to highest applicable taxon)

Usage:
  ./venv/bin/python refine_clavis.py IN.json --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

def primary_lang(clavis: dict) -> str:
    return (clavis.get("language") or ["en"])[0]


def loc(obj: dict | None, lang: str) -> str:
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


# --- quantitative-state parsing ---------------------------------------------

# Parses one quant state label into (lo, hi, unit), with lo=None for -inf
# and hi=None for +inf. Endpoints are integers (the matrix transcoder
# always emits integer mm/g/etc). The unit suffix is whatever follows
# the numbers, trimmed.
QUANT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # "5-19 mm", "5–19 mm", "5 - 19" — closed range. Integer endpoints
    # only; the unit suffix may not start with a digit or dot (so "3.4 m"
    # isn't mistakenly read as int=3 + unit='.4 m').
    (re.compile(r"^(-?\d+)\s*[–\-‒—]\s*(-?\d+)\s*([^\d.\s].*)?$"), "range"),
    # "< 5 mm" / "<5 mm" — open lower
    (re.compile(r"^<\s*(-?\d+)\s*([^\d.\s].*)?$"), "lt"),
    # "> 29 mm" / ">29 mm" — open upper
    (re.compile(r"^>\s*(-?\d+)\s*([^\d.\s].*)?$"), "gt"),
    # "5 mm" — single value
    (re.compile(r"^(-?\d+)\s*([^\d.\s].*)?$"), "single"),
]


def parse_quant_label(label: str) -> tuple[int | None, int | None, str] | None:
    """Return (lo, hi, unit). lo=None means -inf; hi=None means +inf."""
    s = label.strip()
    for pat, kind in QUANT_PATTERNS:
        m = pat.match(s)
        if not m:
            continue
        if kind == "range":
            return int(m.group(1)), int(m.group(2)), (m.group(3) or "").strip()
        if kind == "lt":
            return None, int(m.group(1)) - 1, (m.group(2) or "").strip()
        if kind == "gt":
            return int(m.group(1)) + 1, None, (m.group(2) or "").strip()
        if kind == "single":
            v = int(m.group(1))
            return v, v, (m.group(2) or "").strip()
    return None


def is_quantitative_char(c: dict, lang: str) -> bool:
    """A char counts as quant if every state label parses as a numeric
    range/value. Mixed (some quant, some not) returns False — those
    can't be safely re-binned."""
    states = c.get("states") or []
    if not states:
        return False
    for s in states:
        if parse_quant_label(loc(s.get("title"), lang)) is None:
            return False
    return True


def fmt_atomic(lo: int | None, hi: int | None, unit: str) -> str:
    suffix = f" {unit}" if unit else ""
    if lo is None:
        return f"< {hi + 1}{suffix}"
    if hi is None:
        return f"> {lo - 1}{suffix}"
    if lo == hi:
        return f"{lo}{suffix}"
    return f"{lo}-{hi}{suffix}"


def merge_quantitative_group(members: list[dict], lang: str) -> tuple[list[dict], dict[str, list[str]]] | None:
    """Try to merge a quant duplicate-title group via union-of-breakpoints.

    Returns (atomic_states_list, state_remap{old_state_id → list of atomic state ids it covers})
    or None if states don't all parse or units are inconsistent.
    """
    parsed: dict[str, tuple[int | None, int | None, str]] = {}
    for c in members:
        for s in c["states"]:
            r = parse_quant_label(loc(s.get("title"), lang))
            if r is None:
                return None
            parsed[s["id"]] = r

    units = {u for _, _, u in parsed.values() if u}
    if len(units) > 1:
        return None
    unit = next(iter(units), "")

    has_neg_inf = any(lo is None for lo, _, _ in parsed.values())
    has_pos_inf = any(hi is None for _, hi, _ in parsed.values())
    bps: set[int] = set()
    for lo, hi, _ in parsed.values():
        if lo is not None:
            bps.add(lo)
        if hi is not None:
            bps.add(hi + 1)  # next-bin start (integer convention)
    sorted_bps = sorted(bps)

    # Atomic bins: half-open right [bp[i], bp[i+1]) over integers.
    atomic: list[tuple[int | None, int | None]] = []
    if has_neg_inf and sorted_bps:
        atomic.append((None, sorted_bps[0] - 1))
    for i in range(len(sorted_bps) - 1):
        atomic.append((sorted_bps[i], sorted_bps[i + 1] - 1))
    if has_pos_inf and sorted_bps:
        atomic.append((sorted_bps[-1], None))

    new_states: list[dict] = []
    bin_to_id: dict[tuple[int | None, int | None], str] = {}
    for lo, hi in atomic:
        sid = f"state:{uuid.uuid4().hex}"
        new_states.append({"id": sid, "title": {lang: fmt_atomic(lo, hi, unit)}})
        bin_to_id[(lo, hi)] = sid

    # For each original state with range (olo, ohi), find the atomic bins
    # contained within. None acts as ±inf in the comparison.
    state_remap: dict[str, list[str]] = {}
    for old_sid, (olo, ohi, _) in parsed.items():
        cover: list[str] = []
        for (alo, ahi) in atomic:
            lo_ok = (olo is None) or (alo is not None and alo >= olo)
            hi_ok = (ohi is None) or (ahi is not None and ahi <= ohi)
            if lo_ok and hi_ok:
                cover.append(bin_to_id[(alo, ahi)])
        if not cover:
            return None  # safety: every input state must cover at least one atomic bin
        state_remap[old_sid] = cover

    return new_states, state_remap


def merge_chars_by_title(clavis: dict) -> tuple[dict, list[str]]:
    """Return (refined_clavis, human-readable notes)."""
    lang = primary_lang(clavis)
    # Deep-ish copy so the input dict isn't mutated.
    chars = [dict(c) for c in clavis["characters"]]
    for c in chars:
        c["states"] = [dict(s) for s in c.get("states") or []]

    title_to_idxs: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(chars):
        title_to_idxs[loc(c.get("title"), lang)].append(i)

    notes: list[str] = []
    char_remap: dict[str, str] = {}              # old char id → canonical char id
    state_remap: dict[str, list[str]] = {}       # old state id → [new state ids]
    cat_merged: list[tuple[str, int, int]] = []  # (title, n_in, n_states_added)
    quant_merged: list[tuple[str, int, int]] = []  # (title, n_in, n_atomic_bins)
    quant_skipped: list[tuple[str, int]] = []    # (title, n_in)

    for title, idxs in title_to_idxs.items():
        if len(idxs) <= 1:
            continue
        members = [chars[i] for i in idxs]

        # Quant path: every state in every member must parse as a numeric range/value.
        if all(is_quantitative_char(m, lang) for m in members):
            result = merge_quantitative_group(members, lang)
            if result is not None:
                new_states, q_remap = result
                canonical = chars[idxs[0]]
                canonical["states"] = new_states
                for other_idx in idxs[1:]:
                    char_remap[chars[other_idx]["id"]] = canonical["id"]
                for old_sid, new_sids in q_remap.items():
                    state_remap[old_sid] = new_sids
                quant_merged.append((title, len(idxs), len(new_states)))
                continue
            # Quant merge failed (e.g. inconsistent units across members).
            # Refuse to merge — falling through to categorical would
            # union overlapping numeric ranges into siblings, which
            # violates Protocol 1 (a specimen could satisfy multiple
            # states at once). Disambiguate titles instead so the
            # verifier passes without a false merge.
            quant_skipped.append((title, len(idxs)))
            for i, m_idx in enumerate(idxs, start=1):
                old_title = loc(chars[m_idx].get("title"), lang)
                chars[m_idx]["title"] = {lang: f"{old_title} [{i}]"}
            continue

        # Mixed-type group: same problem. Refuse to merge — disambiguate.
        if any(is_quantitative_char(m, lang) for m in members):
            quant_skipped.append((title, len(idxs)))
            for i, m_idx in enumerate(idxs, start=1):
                old_title = loc(chars[m_idx].get("title"), lang)
                chars[m_idx]["title"] = {lang: f"{old_title} [{i}]"}
            continue

        # Pure-categorical group. Guard against mismerge: extreme
        # label-length spread (e.g. some states are short tokens like
        # 'present' / '5 cm', others are sentence-length descriptions)
        # indicates the same title is being used for genuinely different
        # axes. This is purely structural — no language-specific
        # vocabulary. Refuse to merge and disambiguate.
        union_labels: list[str] = []
        for m_idx in idxs:
            union_labels.extend(loc(s.get("title"), lang)
                                for s in chars[m_idx]["states"])
        lens = [len(l) for l in union_labels if l]
        if lens and max(lens) >= 5 * max(min(lens), 1) and max(lens) > 30:
            quant_skipped.append((title, len(idxs)))
            for i, m_idx in enumerate(idxs, start=1):
                old_title = loc(chars[m_idx].get("title"), lang)
                chars[m_idx]["title"] = {lang: f"{old_title} [{i}]"}
            continue

        canonical = chars[idxs[0]]
        label_to_state: dict[str, str] = {}
        for s in canonical["states"]:
            label_to_state.setdefault(loc(s.get("title"), lang), s["id"])

        states_added = 0
        for other_idx in idxs[1:]:
            other = chars[other_idx]
            char_remap[other["id"]] = canonical["id"]
            for s in other["states"]:
                label = loc(s.get("title"), lang)
                if label in label_to_state:
                    if s["id"] != label_to_state[label]:
                        state_remap[s["id"]] = [label_to_state[label]]
                else:
                    canonical["states"].append(s)
                    label_to_state[label] = s["id"]
                    states_added += 1
        cat_merged.append((title, len(idxs), states_added))

    if not char_remap:
        return clavis, notes

    chars_after = [c for c in chars if c["id"] not in char_remap]
    char_by_id = {c["id"]: c for c in chars_after}

    # Re-point and re-emit statements per (taxon, canonical char) group.
    by_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in clavis["statements"]:
        ch = char_remap.get(s["character"], s["character"])
        new_sids = state_remap.get(s["value"], [s["value"]])
        if s["frequency"] > 0:
            by_group[(s["taxon"], ch)].update(new_sids)
        else:
            by_group.setdefault((s["taxon"], ch), set())

    new_statements: list[dict] = []
    dropped_empty = 0
    for (tx, ch), asserted in by_group.items():
        char = char_by_id.get(ch)
        if char is None:
            continue
        all_state_ids = [s["id"] for s in char["states"]]
        if not asserted:
            dropped_empty += 1
            continue
        n = len(asserted)
        freq_pos = 1.0 if n == 1 else 0.5
        for sid in all_state_ids:
            new_statements.append({
                "id": f"statement:{uuid.uuid4().hex}",
                "taxon": tx,
                "character": ch,
                "value": sid,
                "frequency": freq_pos if sid in asserted else 0,
            })

    refined = dict(clavis)
    refined["characters"] = chars_after
    refined["statements"] = new_statements

    summary_lines: list[str] = []
    if cat_merged:
        n_in = sum(n for _, n, _ in cat_merged)
        n_added = sum(a for _, _, a in cat_merged)
        summary_lines.append(
            f"Categorical merges: {n_in} → {len(cat_merged)} characters "
            f"({n_added} extra states absorbed into canonicals)"
        )
        for title, n_chars, states_added in cat_merged:
            summary_lines.append(f"  {title!r}: {n_chars} → 1 (+{states_added} states)")
    if quant_merged:
        n_in = sum(n for _, n, _ in quant_merged)
        summary_lines.append(
            f"Quantitative merges: {n_in} → {len(quant_merged)} characters "
            f"(union-of-breakpoints atomic binning)"
        )
        for title, n_chars, n_atomic in quant_merged:
            summary_lines.append(f"  {title!r}: {n_chars} → 1 ({n_atomic} atomic bins)")
    if quant_skipped:
        summary_lines.append("Skipped quant merges (unparseable / mixed types):")
        for title, n_in in quant_skipped:
            summary_lines.append(f"  {title!r}: {n_in} chars")
    if dropped_empty:
        summary_lines.append(
            f"Dropped {dropped_empty} empty (taxon, character) groups after re-emission"
        )
    notes.extend(summary_lines)
    return refined, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path, help="Naive Clavis JSON to refine.")
    ap.add_argument("--out", type=Path, required=True, help="Where to write refined Clavis.")
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    refined, notes = merge_chars_by_title(clavis)
    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Characters: {len(clavis['characters'])} → {len(refined['characters'])}")
    print(f"Statements: {len(clavis['statements'])} → {len(refined['statements'])}")
    if notes:
        print("Notes:")
        for n in notes:
            print(f"  {n}")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
