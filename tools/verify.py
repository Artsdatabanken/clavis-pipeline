#!/usr/bin/env python3
"""
Deterministic structural verifier for Clavis identification-key JSON files.

Universal — no language or domain knowledge baked in. Run as:

    python3 verify.py KEY.json [KEY2.json ...] [--collisions-warn] [--without REGEX]

  --collisions-warn   report identical leaf vectors as a warning instead of a violation
                      (for a source that genuinely cannot separate a pair)
  --without REGEX     additionally re-run the collision check with every character whose
                      title matches REGEX removed, reported as warnings (e.g. the audit's
                      geography step: --without "occur|forekomst|region")

Exits 0 if all checks pass, 1 if any structural violation is found.
Prints one diagnostic per violation. Does NOT check semantic atomicity,
quantitative-anchor presence, or source coverage — those require model
reasoning and are handled in phases 2-4 of the audit-clavis-key skill.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def title_of(x) -> str:
    t = x.get("title") or x.get("scientificName") or x.get("label") or ""
    if isinstance(t, dict):
        return " ".join(str(v) for v in t.values())
    return str(t)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_taxa(taxa, parent=None, by_id=None, parent_of=None, leaves=None):
    if by_id is None:
        by_id, parent_of, leaves = {}, {}, []
    for t in taxa:
        by_id[t["id"]] = t
        if parent is not None:
            parent_of[t["id"]] = parent
        kids = t.get("children", [])
        if kids:
            collect_taxa(kids, t["id"], by_id, parent_of, leaves)
        else:
            leaves.append(t["id"])
    return by_id, parent_of, leaves


def main(path: Path, collisions_warn: bool = False, without: str | None = None) -> int:
    errs: list[str] = []
    warns: list[str] = []

    # 1. JSON parses (load succeeded if we got here)
    try:
        d = load(path)
    except Exception as e:
        print(f"FAIL: JSON did not parse: {e}")
        return 1

    # 2. Required top-level fields
    required = [
        "$schema", "identifier", "lastModified", "language", "title",
        "taxa", "characters", "statements", "license",
    ]
    for f in required:
        if f not in d:
            errs.append(f"MISSING-FIELD: top-level field '{f}' is required")

    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1

    # 3. ID prefix conventions
    def check_prefix(entity_type, eid, prefix):
        if not isinstance(eid, str) or not eid.startswith(f"{prefix}:"):
            errs.append(f"BAD-PREFIX: {entity_type} id '{eid}' must start with '{prefix}:'")

    by_id, parent_of, leaves = collect_taxa(d["taxa"])
    for tid in by_id:
        check_prefix("taxon", tid, "taxon")
    for c in d["characters"]:
        check_prefix("character", c["id"], "character")
        for s in (c.get("states") or []):
            check_prefix("state", s["id"], "state")
    for s in d["statements"]:
        check_prefix("statement", s["id"], "statement")

    # 4. UUIDs unique across the file
    seen_ids: dict[str, str] = {}
    def see(kind, eid):
        if eid in seen_ids:
            errs.append(f"DUPLICATE-ID: {eid} used as both {seen_ids[eid]} and {kind}")
        else:
            seen_ids[eid] = kind
    for tid in by_id:
        see("taxon", tid)
    for c in d["characters"]:
        see("character", c["id"])
        for s in (c.get("states") or []):
            see("state", s["id"])
    stmt_ids: set[str] = set()
    for s in d["statements"]:
        if s["id"] in stmt_ids:
            errs.append(f"DUPLICATE-STATEMENT-ID: {s['id']}")
        stmt_ids.add(s["id"])

    # 5. Statements reference existing entities
    char_ids = {c["id"] for c in d["characters"]}
    state_to_char: dict[str, str] = {}
    for c in d["characters"]:
        for s in c.get("states") or []:
            state_to_char[s["id"]] = c["id"]
    state_ids = set(state_to_char.keys())
    numeric_chars = {c["id"] for c in d["characters"] if c.get("type") == "numerical"}
    for s in d["statements"]:
        if s["taxon"] not in by_id:
            errs.append(f"BAD-REF: statement {s['id']} references unknown taxon {s['taxon']}")
        if s["character"] not in char_ids:
            errs.append(f"BAD-REF: statement {s['id']} references unknown character {s['character']}")
        # A numerical character's statements carry value: [min, max] -- a list,
        # not a state id. Validate the interval instead of the state reference.
        if s["character"] in numeric_chars or isinstance(s["value"], list):
            v = s["value"]
            if s["character"] not in numeric_chars:
                errs.append(f"BAD-VALUE: statement {s['id']} has an interval value "
                            f"but character is not type 'numerical'")
            elif (not isinstance(v, list) or len(v) != 2
                  or not all(isinstance(x, (int, float)) for x in v) or v[0] > v[1]):
                errs.append(f"BAD-VALUE: statement {s['id']} numerical value {v!r} "
                            f"must be [min, max] with min <= max")
            continue
        if s["value"] not in state_ids:
            errs.append(f"BAD-REF: statement {s['id']} references unknown state {s['value']}")
        # 6. State must belong to the cited character
        elif s["character"] in char_ids and state_to_char.get(s["value"]) != s["character"]:
            errs.append(
                f"CROSS-CHARACTER: statement {s['id']} value {s['value']} "
                f"is not a state of character {s['character']}"
            )

    # 7. Frequencies must be numbers in [0, 1] (per Clavis schema).
    #    The schema places NO other restriction: 0.95/0.05 is as valid as
    #    0.5/0.5. Graded frequencies carry real information (how often a
    #    taxon shows a value) and must never be rounded away.
    for s in d["statements"]:
        f = s["frequency"]
        if not isinstance(f, (int, float)) or isinstance(f, bool) or not (0 <= f <= 1):
            errs.append(f"BAD-FREQUENCY: statement {s['id']} frequency={f!r} not a number in [0, 1]")

    # 8. (taxon, character) group sanity.
    #    Only one hard rule: an answered group must leave at least one value
    #    reachable. Everything else is a house convention, reported as a
    #    warning so graded frequencies from a source survive untouched.
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for s in d["statements"]:
        groups[(s["taxon"], s["character"])].append(s)
    sciname = {tid: t["scientificName"] for tid, t in by_id.items()}
    char_title = {c["id"]: next(iter(c["title"].values())) for c in d["characters"]}
    char_type = {c["id"]: c.get("type", "exclusive") for c in d["characters"]}
    for (tx, ch), items in groups.items():
        positives = [it for it in items if it["frequency"] > 0]
        if not positives:
            errs.append(
                f"FREQ-EMPTY {sciname[tx]} / {char_title[ch]}: no positive frequency "
                f"in group — the taxon can take no value for this character"
            )
            continue
        for it in items:
            f = it["frequency"]
            if isinstance(f, float) and f not in (0.0, 1.0) and (abs(f - round(f)) < 1e-3):
                warns.append(f"FREQ-ROUNDING {sciname[tx]} / {char_title[ch]}: frequency {f} is rounding noise; write {round(f)}")
        if char_type.get(ch) != "exclusive":
            continue  # non-exclusive: each state is its own yes/no; numerical: one range per taxon
        graded = [it for it in items if it["frequency"] not in (0, 0.5, 1, 0.0, 1.0)]
        if graded:
            continue  # deliberate graded encoding; the convention below does not apply
        ones = sum(1 for it in items if it["frequency"] == 1)
        halfs = sum(1 for it in items if it["frequency"] == 0.5)
        if ones == 1 and halfs == 0:
            continue  # confident
        if ones == 0 and halfs >= 2:
            continue  # uncertain
        if ones == 0 and halfs == 1:
            warns.append(f"FREQ-LONE-HALF {sciname[tx]} / {char_title[ch]}: a single 0.5 with no alternative — did you mean 1?")
        elif ones >= 1 and halfs >= 1:
            warns.append(f"FREQ-MIXED {sciname[tx]} / {char_title[ch]}: 1 mixed with 0.5 — use graded frequencies if that is what the source says")
        elif ones > 1:
            warns.append(f"FREQ-MULTI-ONE {sciname[tx]} / {char_title[ch]}: more than one frequency of 1 in an exclusive character")

    # 8a. Numerical characters: unit present, min <= max, every statement's
    #     range inside the character's range and lo <= hi, exactly one
    #     statement per (taxon, character).
    for c in d["characters"]:
        if c.get("type") != "numerical":
            continue
        t = char_title[c["id"]]
        if not c.get("unit"):
            warns.append(f"NUM-UNIT {t}: numerical character without a unit")
        if "min" in c and "max" in c and c["min"] > c["max"]:
            errs.append(f"NUM-RANGE {t}: character min {c['min']} > max {c['max']}")
    for (tx, ch), items in groups.items():
        if char_type.get(ch) == "numerical" and len(items) > 1:
            errs.append(f"NUM-MULTI {sciname[tx]} / {char_title[ch]}: {len(items)} statements for one taxon; a numerical character takes one [min, max]")

    # 8b. Character type must be one the schema allows. All three are legal:
    #     exclusive (default), non-exclusive, numerical. A numerical character
    #     carries min/max/stepSize/unit instead of states, and its statements
    #     take value = [min, max].
    for c in d["characters"]:
        ctype = c.get("type", "exclusive")
        if ctype not in ("exclusive", "non-exclusive", "numerical"):
            errs.append(
                f"BAD-CHARACTER-TYPE: character '{char_title[c['id']]}' has "
                f"type '{ctype}' — must be exclusive, non-exclusive or numerical"
            )
        if ctype == "numerical":
            missing = [k for k in ("min", "max", "stepSize", "unit") if k not in c]
            if missing:
                errs.append(
                    f"NUMERICAL-INCOMPLETE: character '{char_title[c['id']]}' is "
                    f"numerical but lacks {', '.join(missing)}"
                )

    # 9. State titles unique within a character (per language)
    for c in d["characters"]:
        seen_per_lang: dict[str, dict[str, str]] = defaultdict(dict)
        for s in (c.get("states") or []):
            for lang, title in (s.get("title") or {}).items():
                if title in seen_per_lang[lang]:
                    errs.append(
                        f"DUPLICATE-STATE-TITLE: character '{char_title[c['id']]}' "
                        f"has duplicate state title '{title}' in language '{lang}'"
                    )
                else:
                    seen_per_lang[lang][title] = s["id"]

    # 10. (removed) Character titles need not be unique. Characters are
    #     identified by id, and a matrix key has no branches: every character is
    #     an independent question that just filters the candidate set, so there
    #     is no "right one" for the user to pick and nothing to confuse. A key
    #     built from couplets asks the same trait at several points with
    #     different state sets, and each of them is correctly named after the
    #     trait. Renaming one to disambiguate would label it by its place in the
    #     key instead of by what the user observes.

    # 11. Discriminability: per-leaf full vectors with inheritance must be unique
    direct: dict[tuple[str, str], frozenset[str]] = {}
    for (tx, ch), items in groups.items():
        # A numerical character's value is a [min, max] list -- unhashable, so
        # freeze it to a tuple before it goes into the vector.
        positive = frozenset(
            tuple(it["value"]) if isinstance(it["value"], list) else it["value"]
            for it in items if it["frequency"] > 0)
        direct[(tx, ch)] = positive

    # No overriding in Clavis: a statement on an ancestor holds for every
    # descendant, and a descendant restating the same character is invalid --
    # the interface never surfaces the conflict, the key is simply broken.
    stated = {}
    for s in d["statements"]:
        stated.setdefault(s["taxon"], set()).add(s["character"])
    for tx in by_id:
        chain, x = [], parent_of.get(tx)
        while x:
            chain.append(x)
            x = parent_of.get(x)
        for ch in stated.get(tx, ()):
            for anc in chain:
                if ch in stated.get(anc, ()):
                    errs.append(
                        f"INHERIT-CONFLICT: {sciname.get(tx, tx)} restates character "
                        f"'{char_title.get(ch, ch)}' already stated on ancestor "
                        f"{sciname.get(anc, anc)} - there is no overriding in Clavis"
                    )

    def vector(leaf_id):
        v = {}
        for c in d["characters"]:
            cur = leaf_id
            value = None
            while True:
                if (cur, c["id"]) in direct:
                    value = direct[(cur, c["id"])]
                    break
                if cur not in parent_of:
                    break
                cur = parent_of[cur]
            v[c["id"]] = value
        return v

    def find_collisions(drop: set[str], sink: list[str], suffix: str):
        seen_vec: dict[tuple, str] = {}
        for lid in leaves:
            v = {c: s for c, s in vector(lid).items() if c not in drop}
            key = tuple(sorted((c, tuple(sorted(s)) if s else None) for c, s in v.items()))
            if key in seen_vec:
                sink.append(
                    f"COLLISION{suffix}: leaves {sciname[seen_vec[key]]} and {sciname[lid]} "
                    f"have identical character vectors — not pairwise discernible"
                )
            else:
                seen_vec[key] = lid

    find_collisions(set(), warns if collisions_warn else errs, "")
    if without:
        rx = re.compile(without, re.I)
        drop = {c["id"] for c in d["characters"] if rx.search(title_of(c))}
        find_collisions(drop, warns, f" (without /{without}/, {len(drop)} characters removed)")

    # 12. Coverage hints: a leaf with no statements at all, or a character no
    #     statement uses, is legal but almost always an omission.
    for lid in leaves:
        if not any(s for s in vector(lid).values()):
            warns.append(f"EMPTY-LEAF: {sciname.get(lid, lid)} has no statements, own or inherited")
    used = {s["character"] for s in d["statements"]}
    for c in d["characters"]:
        if c["id"] not in used:
            warns.append(f"UNUSED-CHARACTER: '{char_title.get(c['id'], c['id'])}' is never used")

    # Report
    if errs:
        print(f"verify.py: {len(errs)} structural violation(s) found in {path}\n")
        for e in errs:
            print(f"  {e}")
        if warns:
            print(f"\n  ({len(warns)} convention warning(s) — not violations)")
            for w in warns:
                print(f"  WARN: {w}")
        return 1
    counts = (
        f"taxa={len(by_id)}, leaves={len(leaves)}, "
        f"characters={len(d['characters'])}, statements={len(d['statements'])}"
    )
    if warns:
        print(f"verify.py: PASS with {len(warns)} convention warning(s)  ({counts})  {path}")
        for w in warns:
            print(f"  WARN: {w}")
        return 0
    print(f"verify.py: PASS  ({counts})  {path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="+", type=Path)
    ap.add_argument("--collisions-warn", action="store_true")
    ap.add_argument("--without", metavar="REGEX")
    a = ap.parse_args()
    sys.exit(max(main(p, a.collisions_warn, a.without) for p in a.keys))
