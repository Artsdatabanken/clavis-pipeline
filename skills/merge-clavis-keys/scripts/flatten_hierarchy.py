#!/usr/bin/env python3
"""Flatten a Clavis taxa tree to root -> root's direct children -> leaves
(for the rodent key: species directly under families). Identification stays
bit-for-bit identical: each leaf's EFFECTIVE values are computed first, the
middle levels are removed, then groups shared by every leaf under one child
of the root are hoisted back onto that child (and, if shared by all, to root).
Whole frequency vectors move together. Aborts if any leaf's effective values
change.

Usage: flatten_hierarchy.py IN.json OUT.json
"""
import json, sys, collections, uuid

inp, outp = sys.argv[1], sys.argv[2]
d = json.load(open(inp, encoding="utf-8"))
byt, par = {}, {}
def w(ts, p=None):
    for t in ts: byt[t["id"]] = t; par[t["id"]] = p; w(t.get("children", []), t["id"])
w(d["taxa"])
grp = collections.defaultdict(dict)
for s in d["statements"]:
    grp[s["taxon"]].setdefault(s["character"], {})[s["value"]] = s["frequency"]
def eff(t):
    ch, x = [], t
    while x: ch.append(x); x = par[x]
    o = {}
    for a in reversed(ch): o.update({c: dict(g) for c, g in grp.get(a, {}).items()})
    return o
leaves = [i for i, t in byt.items() if not t.get("children")]
before = {l: eff(l) for l in leaves}
root = d["taxa"][0]
groups = root["children"]
of = {}
def collect(t, g):
    if t.get("children"):
        for c in t["children"]: collect(c, g)
    else: of[t["id"]] = g
for g in groups:
    for c in g["children"]: collect(c, g["id"])
for g in groups:
    ks = [byt[l] for l in leaves if of[l] == g["id"]]
    ks.sort(key=lambda t: t["scientificName"])
    g["children"] = ks
newgrp = {l: dict(before[l]) for l in leaves}
ggrp, rgrp = collections.defaultdict(dict), {}
for g in groups:
    ks = [l for l in leaves if of[l] == g["id"]]
    for c in {c for l in ks for c in newgrp[l]}:
        vs = [newgrp[l].get(c) for l in ks]
        if all(v is not None for v in vs) and all(v == vs[0] for v in vs):
            ggrp[g["id"]][c] = vs[0]
            for l in ks: del newgrp[l][c]
for c in {c for g in groups for c in ggrp[g["id"]]}:
    vs = [ggrp[g["id"]].get(c) for g in groups]
    if all(v is not None for v in vs) and all(v == vs[0] for v in vs):
        rgrp[c] = vs[0]
        for g in groups: del ggrp[g["id"]][c]
out = []
def emit(t, gg):
    for c, st in gg.items():
        for v, fr in st.items():
            out.append({"id": "statement:" + uuid.uuid4().hex, "taxon": t,
                        "character": c, "value": v, "frequency": fr})
emit(root["id"], rgrp)
for g in groups: emit(g["id"], ggrp[g["id"]])
for l in leaves: emit(l, newgrp[l])
d["statements"] = out
byt, par = {}, {}; w(d["taxa"])
grp = collections.defaultdict(dict)
for s in d["statements"]:
    grp[s["taxon"]].setdefault(s["character"], {})[s["value"]] = s["frequency"]
bad = [l for l in leaves if eff(l) != before[l]]
assert not bad, "effective values changed for %r" % [byt[b]["scientificName"] for b in bad]
json.dump(d, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"taxa -> {len(byt)} (root + {len(groups)} groups + {len(leaves)} leaves), "
      f"{len(out)} statements, effective values unchanged")
