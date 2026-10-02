#!/usr/bin/env python3
"""Flag states a person with one specimen and the guide could not pick:
comparatives, bundles, and characters with too many shades.

Usage: flag_undeterminable.py KEY.json --out flags.md [--lang nb] [--max-states 6]

Checks (deterministic; the agent judges only what is flagged):
  COMPARATIVE  state or character title with a comparison word and no number
               ("darker than the field vole", "larger", "lysere", "enn", "than")
  BUNDLE       state label joining alternatives ("brown or grey", "eller", "/")
  SHADES       exclusive categorical character with more than --max-states states
  RELATIVE     quantity words without a number or unit ("small", "long", "stor")
  NUMERIC-AS-STATES  states that parse as numeric bins in a categorical character:
               should be a numerical character
Numerical characters pass by construction (a measurement needs no comparison).
Word lists live in references/determinability-words.json per language.
"""
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("key"); ap.add_argument("--out", required=True)
ap.add_argument("--lang", default=None); ap.add_argument("--max-states", type=int, default=6)
a = ap.parse_args()
d = json.load(open(a.key, encoding="utf-8"))
lang = a.lang or (d.get("language") or ["en"])[0]
T = lambda o: next(iter((o.get("title") or {}).values()), "")
W = json.loads((HERE.parent / "references" / "determinability-words.json").read_text(encoding="utf-8"))
words = W.get(lang) or W.get("en")
NUM = re.compile(r"\d")
def has(text, lst):
    t = f" {text.lower()} "
    return any(f" {w.lower()} " in t for w in lst)
NUMBIN = re.compile(r"^(under|over|opptil|<|>|\d)")

flags = []
for c in d["characters"]:
    t = T(c)
    if c.get("type") == "numerical": continue
    labs = [T(s) for s in (c.get("states") or [])]
    if c.get("type", "exclusive") == "exclusive" and len(labs) > a.max_states:
        flags.append(("SHADES", t, "", f"{len(labs)} states: {' / '.join(labs)}"))
    if has(t, words["comparative"]) and not NUM.search(t):
        flags.append(("COMPARATIVE", t, "", "character title compares to something not in front of the user"))
    if len(labs) >= 2 and all(NUMBIN.match(l.lower()) for l in labs):
        flags.append(("NUMERIC-AS-STATES", t, "", "every state is a numeric bin; make this a numerical character"))
    for l in labs:
        if has(l, words["comparative"]) and not NUM.search(l):
            flags.append(("COMPARATIVE", t, l, "needs a second specimen or experience to answer"))
        if has(l, words["bundle"]) or "/" in l:
            flags.append(("BUNDLE", t, l, "lists alternatives; one state per observable value"))
        if has(l, words["relative"]) and not NUM.search(l):
            flags.append(("RELATIVE", t, l, "size or degree word without a number"))

out = [f"# Determinability flags for {Path(a.key).name}", "",
       "Criterion: can one person, with one specimen and this guide, no comparison specimen and no experience, pick the state? Decide each flagged row: merge, rewrite in absolute terms, convert to numerical, split, or keep with a one-line reason.", "",
       "| kind | character | state | why |", "|---|---|---|---|"]
for k, t, l, why in flags:
    out.append(f"| {k} | {t} | {l} | {why} |")
out.append(""); out.append(f"{len(flags)} flags on {len(d['characters'])} characters. Decisions go in decisions.json for refine-clavis-key/scripts/apply_state_merges.py (merges) and a rename map for relabels.")
open(a.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"{len(flags)} flags -> {a.out}")
