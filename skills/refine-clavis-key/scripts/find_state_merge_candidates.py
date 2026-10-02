#!/usr/bin/env python3
"""Phase 2 NARROW step: list within-character state pairs that are
candidates for synonymous-state merging.

Output is a Markdown report with one section per character that has any
flagged pairs. Claude reads the report, decides per row, and writes a
decisions.json that `apply_state_merges.py` consumes.

Quantitative characters (every state label parses as a numeric range/
value) are skipped — their atomic bins share unit tokens and produce
spurious Jaccard matches.

A pair within a categorical character is flagged if any of:
  - Token Jaccard ≥ JACCARD_THRESHOLD (default 0.5)
  - One label is a substring of the other AND size diff ≤ SUBSTR_DIFF (3)
    — catches "sep" / "sept", "bruin" / "bruinrood" but not specificity
    differences like "groen" / "groen met vele kleine stippels".
  - Edit distance / max label length ≤ EDIT_RATIO (0.3), only for labels
    ≥ MIN_EDIT_LEN (6) characters — short labels generate too much noise.

Pairs are sorted by token Jaccard descending within each character.

Usage:
  ./venv/bin/python find_state_merge_candidates.py IN.json --out candidates.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

JACCARD_THRESHOLD = 0.5
SUBSTR_DIFF = 3
EDIT_RATIO = 0.3
MIN_EDIT_LEN = 6
WORD_RE = re.compile(r"\w+", re.UNICODE)

# --- quantitative parser (mirror of refine_clavis.py logic; we skip
# quant chars to avoid unit-token Jaccard noise). Kept inline so the
# script has no cross-asset import.
_QUANT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(-?\d+)\s*[–\-‒—]\s*(-?\d+)\s*(\S.*)?$"), "range"),
    (re.compile(r"^<\s*(-?\d+)\s*(\S.*)?$"), "lt"),
    (re.compile(r"^>\s*(-?\d+)\s*(\S.*)?$"), "gt"),
    (re.compile(r"^(-?\d+)\s*(\S.*)?$"), "single"),
]


def parses_as_quant(label: str) -> bool:
    s = label.strip()
    return any(pat.match(s) for pat, _ in _QUANT_PATTERNS)


def is_quantitative_char(c: dict, lang: str) -> bool:
    states = c.get("states") or []
    if not states:
        return False
    for s in states:
        title = (s.get("title") or {}).get(lang) or next(iter((s.get("title") or {}).values()), "")
        if not parses_as_quant(title.strip()):
            return False
    return True


def primary_lang(clavis: dict) -> str:
    return (clavis.get("language") or ["en"])[0]


def loc(obj: dict | None, lang: str) -> str:
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


def tokens(s: str) -> set[str]:
    return set(WORD_RE.findall(s.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[-1]


def flag_pair(la: str, lb: str) -> tuple[bool, float, int, bool]:
    """Return (flagged, jaccard, edit, substring_flag)."""
    al, bl = la.lower(), lb.lower()
    tok_a, tok_b = tokens(al), tokens(bl)
    jac = jaccard(tok_a, tok_b)
    edit = levenshtein(al, bl)
    max_len = max(len(al), len(bl))
    size_diff = abs(len(al) - len(bl))
    substr = (al in bl or bl in al) and al != bl

    if jac >= JACCARD_THRESHOLD:
        return True, jac, edit, substr
    if substr and size_diff <= SUBSTR_DIFF:
        return True, jac, edit, substr
    if max_len >= MIN_EDIT_LEN and edit / max_len <= EDIT_RATIO:
        return True, jac, edit, substr
    return False, jac, edit, substr


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, default=Path("merge_candidates.md"))
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    lang = primary_lang(clavis)

    body: list[str] = []
    n_pairs = 0
    n_chars = 0
    n_quant_skipped = 0

    for c in clavis["characters"]:
        title = loc(c.get("title"), lang) or "(untitled)"
        states = c.get("states") or []

        if is_quantitative_char(c, lang):
            n_quant_skipped += 1
            continue

        candidates: list[tuple] = []
        for i in range(len(states)):
            for j in range(i + 1, len(states)):
                la = loc(states[i].get("title"), lang)
                lb = loc(states[j].get("title"), lang)
                if not la or not lb or la == lb:
                    continue
                flagged, jac, edit, substr = flag_pair(la, lb)
                if flagged:
                    candidates.append((states[i], states[j], la, lb, jac, edit, substr))

        if not candidates:
            continue
        n_chars += 1
        n_pairs += len(candidates)
        candidates.sort(key=lambda r: -r[4])
        body.append(f"\n## {title}")
        body.append(f"\nCharacter ID: `{c['id']}`\n")
        body.append("| State A | State A id | State B | State B id | Jaccard | Edit | Substring |")
        body.append("|---|---|---|---|---|---|---|")
        for sa, sb, la, lb, jac, edit, substr in candidates:
            body.append(
                f"| {la!r} | `{sa['id']}` | {lb!r} | `{sb['id']}` "
                f"| {jac:.2f} | {edit} | {'yes' if substr else 'no'} |"
            )

    header = [
        f"# State-merge candidates: {args.infile.name}",
        "",
        f"Triggers: token Jaccard ≥ {JACCARD_THRESHOLD}, "
        f"substring with size diff ≤ {SUBSTR_DIFF}, "
        f"or edit/max-len ≤ {EDIT_RATIO} (labels ≥ {MIN_EDIT_LEN} chars).",
        f"Skipped {n_quant_skipped} quantitative characters.",
        f"\n{n_pairs} candidate pairs across {n_chars} characters.",
    ]
    if n_pairs == 0:
        header.append("\n_No candidate pairs above threshold — Phase 2 has nothing to do._\n")

    args.out.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  {n_pairs} pairs in {n_chars} characters (skipped {n_quant_skipped} quant chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
