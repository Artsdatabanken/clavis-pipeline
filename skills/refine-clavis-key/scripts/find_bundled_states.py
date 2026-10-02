#!/usr/bin/env python3
"""Phase 3 NARROW step: list states whose labels look like they bundle
distinguishable values ("red, sometimes white", "bruin/grijs").

Language-neutral signals only (no word lists):
  - a "/" or "," inside the label
  - the label contains another sibling state's whole label as a word sequence
    ("brown or grey" contains "brown"): the longer one is probably a bundle
  - the label has three or more words while a sibling has one: a qualified or
    compound value next to an atomic one
Quantitative characters (every state parses as a number or range) are skipped.

Output: a markdown report the model reads to decide per flagged state whether
to split into atomic labels, with sibling-state context. Decisions JSON format:
  {"splits": [{"state_id": "...", "atomic_labels": ["...", ...]}]}

Usage:
  find_bundled_states.py IN.json --out bundles.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_QUANT = re.compile(r"^\s*[<>≤≥]?\s*-?\d")


def loc(obj, lang):
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    lang = (clavis.get("language") or ["und"])[0]
    sections = []
    n = 0
    for c in clavis["characters"]:
        states = c.get("states") or []
        labels = [(s["id"], loc(s.get("title"), lang)) for s in states]
        if not labels or all(_QUANT.match(l) for _, l in labels if l):
            continue
        flagged = []
        for sid, l in labels:
            low = f" {l.lower()} "
            why = []
            if "/" in l or "," in l:
                why.append("contains / or ,")
            for sid2, l2 in labels:
                if sid2 != sid and l2 and len(l2) >= 3 and f" {l2.lower()} " in low and len(l) > len(l2):
                    why.append(f"contains sibling label '{l2}'")
            if len(l.split()) >= 3 and any(len(l2.split()) == 1 for _, l2 in labels):
                why.append("three or more words beside a one-word sibling")
            if why:
                flagged.append((sid, l, "; ".join(dict.fromkeys(why))))
        if flagged:
            n += len(flagged)
            sections.append(f"## {loc(c.get('title'), lang)} (`{c['id']}`)\n\nStates: " + " | ".join(l for _, l in labels) + "\n\n" +
                            "\n".join(f"- `{sid}` **{l}**: {why}" for sid, l, why in flagged))
    out = f"# Bundled-state candidates: {args.infile.name}\n\n{n} candidate states. For each, decide: split into atomic labels (list them), or keep (one line why).\n\n" + "\n\n".join(sections) + "\n"
    args.out.write_text(out, encoding="utf-8")
    print(f"{n} candidates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
