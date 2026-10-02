#!/usr/bin/env python3
"""Flag states a person with one specimen and the guide could not pick.
Language-neutral: the flags come from the claims behind the statements and
from the key's structure, never from word lists.

Usage: flag_undeterminable.py KEY.json --out flags.md [--claims claims.jsonl --provenance provenance.jsonl] [--max-states 6]

Checks:
  COMPARATIVE   a state all of whose supporting claims are marked `comparative`
                by the harvester (compares to something not in front of the user)
  BUNDLE        a state whose supporting claims list several `values` (the
                source said "A or B"; one state per value is required)
  RELATIVE      a categorical state on a trait for which other claims carry
                numbers (the source measures it elsewhere; words like "small"
                have a number behind them and should become a range)
  SHADES        an exclusive categorical character with more than --max-states
                states
  NUMERIC-AS-STATES  every state label of a categorical character starts with
                a number or a comparison symbol: should be a numerical character
Without --claims/--provenance only SHADES and NUMERIC-AS-STATES are checked.
Numerical characters pass by construction.
"""
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("key"); ap.add_argument("--out", required=True)
ap.add_argument("--claims", type=Path); ap.add_argument("--provenance", type=Path)
ap.add_argument("--max-states", type=int, default=6)
a = ap.parse_args()
d = json.load(open(a.key, encoding="utf-8"))
T = lambda o: next(iter((o.get("title") or {}).values()), "")
NUMBIN = re.compile(r"^\s*[<>≤≥]?\s*\d")

claims = {}
if a.claims and a.claims.exists():
    for l in a.claims.read_text(encoding="utf-8").splitlines():
        if l.strip():
            c = json.loads(l); claims[c["id"]] = c
prov = defaultdict(list)
if a.provenance and a.provenance.exists():
    for l in a.provenance.read_text(encoding="utf-8").splitlines():
        if l.strip():
            p = json.loads(l); prov[p["statement"]] = p.get("claims", [])
stmt_by_state = defaultdict(list)
for s in d["statements"]:
    if not isinstance(s["value"], list):
        stmt_by_state[s["value"]].append(s["id"])
numeric_traits = {c["trait"].lower() for c in claims.values() if c.get("value_num")}

flags = []
for c in d["characters"]:
    t = T(c)
    if c.get("type") == "numerical":
        continue
    labs = [T(s) for s in (c.get("states") or [])]
    if c.get("type", "exclusive") == "exclusive" and len(labs) > a.max_states:
        flags.append(("SHADES", t, "", f"{len(labs)} states: {' / '.join(labs)}"))
    if len(labs) >= 2 and all(NUMBIN.match(l) for l in labs):
        flags.append(("NUMERIC-AS-STATES", t, "", "every state starts with a number; make this a numerical character"))
    for s in c.get("states") or []:
        backing = [claims[cid] for sid in stmt_by_state.get(s["id"], []) for cid in prov.get(sid, []) if cid in claims]
        if not backing:
            continue
        if all(cl.get("qualifier") == "comparative" for cl in backing):
            flags.append(("COMPARATIVE", t, T(s), "every supporting claim compares to another taxon or specimen"))
        if any(isinstance(cl.get("values"), list) and len(cl["values"]) > 1 for cl in backing):
            flags.append(("BUNDLE", t, T(s), "a supporting claim lists several values; one state per value"))
        if not any(cl.get("value_num") for cl in backing) and all(cl["trait"].lower() in numeric_traits for cl in backing):
            flags.append(("RELATIVE", t, T(s), "the source gives numbers for this trait elsewhere; this state has none"))

out = [f"# Determinability flags for {Path(a.key).name}", "",
       "Criterion: can one person, with one specimen and this guide, no comparison specimen and no experience, pick the state? Decide each flagged row: merge, rewrite in absolute terms, convert to numerical, split, or keep with a one-line reason.", "",
       "| kind | character | state | why |", "|---|---|---|---|"]
for k, t, l, why in flags:
    out.append(f"| {k} | {t} | {l} | {why} |")
out.append(""); out.append(f"{len(flags)} flags on {len(d['characters'])} characters" + ("" if claims else " (structure only: pass --claims and --provenance for the claim-based checks)") + ".")
open(a.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"{len(flags)} flags -> {a.out}")
