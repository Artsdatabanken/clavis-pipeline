#!/usr/bin/env python3
"""Location characters are a last resort: keep one only for the species of a
pair that needs it (the pair would lose its last separator, or drop from >=3
routes to fewer, without it); strip its statements from every other species;
drop the character entirely when no pair needs it.

Usage: cleanup_location.py IN.json OUT.json --match "^(Utbredelse|Forekomst|Occurs|Distribution)" --removed removed.json

Writes removed.json entries in the roundtrip.py format:
  {"<title>": {"reason": "...", "species": "all" | [names stripped], "kept_for": [names]}}
Decided by measurement, not by hand.
"""
import argparse, collections, importlib.util, itertools, json, os, re, sys

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("outp")
ap.add_argument("--match", required=True, help="regex on character titles")
ap.add_argument("--removed", required=True)
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
spec_ = importlib.util.spec_from_file_location("redundancy", os.path.join(HERE, "redundancy.py"))
R = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(R)
T = lambda o: next(iter((o.get("title") or {}).values()), "")
d = json.load(open(a.inp, encoding="utf-8"))
rx = re.compile(a.match, re.I)
loc = {c["id"]: T(c) for c in d["characters"] if rx.search(T(c))}
if not loc:
    json.dump({}, open(a.removed, "w"), ensure_ascii=False)
    json.dump(d, open(a.outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("no location characters"); sys.exit(0)

_, lv, E, taxa = R.load(a.inp)
sep_all, *_ = R.analyse(d, lv, E, {})
# separability without ALL location characters
d2 = json.loads(json.dumps(d)); d2["characters"] = [c for c in d2["characters"] if c["id"] not in loc]
d2["statements"] = [s for s in d2["statements"] if s["character"] not in loc]
json.dump(d2, open(a.outp + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
_, lv2, E2, _ = R.load(a.outp + ".tmp"); sep_none, *_ = R.analyse(d2, lv2, E2, {})
os.remove(a.outp + ".tmp")
name = {i: t["scientificName"] for i, t in taxa.items()}
needed = collections.defaultdict(set)   # char id -> species needing it
for pair, routes in sep_all.items():
    r2 = sep_none.get(pair, set())
    if (routes and not r2) or (len(routes) >= 3 and len(r2) < 3):
        for c in routes - r2:
            needed[c].update(pair)
removed = {}
keep_stmts = []
stripped = collections.defaultdict(set)
for s in d["statements"]:
    c = s["character"]
    if c not in loc: keep_stmts.append(s); continue
    if s["taxon"] in needed.get(c, ()): keep_stmts.append(s)
    else: stripped[c].add(name.get(s["taxon"], s["taxon"]))
for c, t in loc.items():
    if c in needed:
        removed[t] = {"reason": "location-bound; kept only for the species whose pairs need it", "species": sorted(stripped[c]), "kept_for": sorted(name[x] for x in needed[c])}
    else:
        removed[t] = {"reason": "location-bound; no species pair needs it (measured: no pair loses its last route or drops below 3)", "species": "all"}
d["statements"] = keep_stmts
d["characters"] = [c for c in d["characters"] if c["id"] not in loc or c["id"] in needed]
json.dump(d, open(a.outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(removed, open(a.removed, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for t, v in removed.items():
    print(f"{t}: " + ("dropped" if v["species"] == "all" else f"kept for {', '.join(v['kept_for'])}; stripped from {len(v['species'])} species"))
