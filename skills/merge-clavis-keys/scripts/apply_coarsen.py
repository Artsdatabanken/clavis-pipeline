#!/usr/bin/env python3
"""Apply a state-coarsening plan {"Character": {"old label": "new label", ...}}.

Frequencies are SUMMED, not maxed: states of a character are mutually
exclusive, so P(A or B) = P(A) + P(B). A group that ends above 1 (the source
admitted three values and two of them merged) is scaled back to sum 1 with
relative weights preserved.

Usage: apply_coarsen.py IN.json OUT.json PLAN.json
"""
import json, sys, collections
inp, outp, planp = sys.argv[1:4]
d = json.load(open(inp, encoding="utf-8"))
plan = json.load(open(planp, encoding="utf-8"))
T = lambda o: next(iter(o["title"].values()))
lang = (d.get("language") or ["nb"])[0]

remap, before = {}, sum(len(c.get("states") or []) for c in d["characters"])
skipped = []
for c in d["characters"]:
    p = plan.get(T(c))
    if not p: continue
    if c.get("type", "exclusive") != "exclusive":
        skipped.append(T(c)); continue  # non-exclusive: states are separate yes/no claims; numerical: no states
    keep = {}
    for s in list(c["states"]):
        new = p.get(T(s))
        if not new: continue
        if new in keep: remap[s["id"]] = keep[new]
        else: keep[new] = s["id"]; s["title"] = {lang: new}
    c["states"] = [s for s in c["states"] if s["id"] not in remap]

acc = collections.OrderedDict()
for s in d["statements"]:
    v = s["value"] if isinstance(s["value"], list) else remap.get(s["value"], s["value"])
    k = (s["taxon"], s["character"], json.dumps(v))
    if k in acc: acc[k]["frequency"] = round(acc[k]["frequency"] + s["frequency"], 4)
    else: s = dict(s); s["value"] = v; acc[k] = s
d["statements"] = list(acc.values())

exclusive = {c["id"] for c in d["characters"] if c.get("type", "exclusive") == "exclusive"}
grp = collections.defaultdict(list)
for s in d["statements"]:
    if s["character"] in exclusive: grp[(s["taxon"], s["character"])].append(s)
rescaled = 0
for k, v in grp.items():
    tot = sum(x["frequency"] for x in v)
    if round(tot, 4) > 1.0:
        rescaled += 1
        for x in v: x["frequency"] = round(x["frequency"] / tot, 4)
for s in d["statements"]:
    f = s["frequency"]
    if isinstance(f, float) and abs(f - round(f)) < 1e-3: s["frequency"] = int(round(f))
json.dump(d, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
after = sum(len(c.get("states") or []) for c in d["characters"])
print(f"states {before} -> {after} ({len(remap)} merged); {len(d['statements'])} statements; "
      f"{rescaled} groups rescaled to sum 1" + (f"; skipped (not exclusive): {', '.join(skipped)}" if skipped else ""))
