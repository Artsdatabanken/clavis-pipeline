#!/usr/bin/env python3
"""Phase 4 NARROW step: list characters whose states seem to mix more than one
observable axis (colour states beside pattern states; "with spots" beside
"green").

Language-neutral signals only (no word lists):
  - two state labels that differ in exactly one word, with the shared words
    forming most of the label ("with spots" / "without spots" is one axis of
    presence; "green" beside them is another)
  - a label whose first word is shared with another label's first word while
    a third label shares no word with either
  - a mix of one-word labels and multi-word labels in the same character
Quantitative characters are skipped. The model judges every flagged character
and writes the split decisions for apply_character_split.py.

Usage:
  find_multi_axis_characters.py IN.json --out multi_axis.md
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

_QUANT = re.compile(r"^\s*[<>≤≥]?\s*-?\d")


def loc(obj, lang):
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


def words(l):
    return [w for w in re.split(r"[\s\-–/,;:()]+", l.lower()) if w]


def flag_character(labels):
    why = []
    ws = [words(l) for l in labels]
    for (a, wa), (b, wb) in itertools.combinations(zip(labels, ws), 2):
        if len(wa) == len(wb) and len(wa) >= 2 and sum(x != y for x, y in zip(wa, wb)) == 1:
            why.append(f"'{a}' and '{b}' differ in one word: one axis; check the other states belong to it")
    firsts = {}
    for l, w in zip(labels, ws):
        if w:
            firsts.setdefault(w[0], []).append(l)
    shared = [g for g in firsts.values() if len(g) >= 2]
    if shared:
        others = [l for l, w in zip(labels, ws) if w and not any(set(w) & set(words(x)) for g in shared for x in g if x != l)]
        if others:
            why.append(f"states sharing a first word ({', '.join(shared[0][:3])}) beside unrelated states ({', '.join(others[:3])})")
    if any(len(w) == 1 for w in ws) and any(len(w) >= 2 for w in ws) and len(labels) >= 3:
        why.append("one-word and multi-word states mixed")
    return why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    lang = (clavis.get("language") or ["und"])[0]
    sections, n = [], 0
    for c in clavis["characters"]:
        labels = [loc(s.get("title"), lang) for s in (c.get("states") or [])]
        labels = [l for l in labels if l]
        if len(labels) < 2 or all(_QUANT.match(l) for l in labels):
            continue
        why = flag_character(labels)
        if why:
            n += 1
            sections.append(f"## {loc(c.get('title'), lang)} (`{c['id']}`)\n\nStates: " + " | ".join(labels) + "\n\n" + "\n".join(f"- {w}" for w in dict.fromkeys(why)))
    out = f"# Multi-axis candidates: {args.infile.name}\n\n{n} candidate characters. For each, decide: split into one character per axis (name the axes and assign every state), or keep (one line why).\n\n" + "\n\n".join(sections) + "\n"
    args.out.write_text(out, encoding="utf-8")
    print(f"{n} candidates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
