#!/usr/bin/env python3
"""Repair inheritance conflicts: the same character stated on both a taxon and
a descendant of it. Clavis has NO overriding -- a parent's statement binds every
descendant, and a child restating the character makes the key invalid.

Repair: take the statement off the ancestor and copy it onto every child that
does not state that character itself (recursively, so deeper conflicts resolve
too). Every leaf keeps exactly the effective values it had; the script aborts
if a single one changes. Whole frequency vectors move together -- graded
frequencies (0.95/0.05) are never flattened.

Usage: fix_inherit.py IN.json OUT.json
"""
import json, sys, collections, uuid

inp, outp = sys.argv[1], sys.argv[2]
d = json.load(open(inp, encoding="utf-8"))
byt, par, kids = {}, {}, collections.defaultdict(list)
def w(ts, p=None):
    for t in ts:
        byt[t["id"]] = t; par[t["id"]] = p
        if p: kids[p].append(t["id"])
        w(t.get("children", []), t["id"])
w(d["taxa"])
grp = collections.defaultdict(dict)
for s in d["statements"]:
    grp[s["taxon"]].setdefault(s["character"], {})[s["value"]] = s["frequency"]
def desc(t):
    o = []
    for k in kids[t]: o.append(k); o += desc(k)
    return o
def eff(t):
    ch, x = [], t
    while x: ch.append(x); x = par[x]
    o = {}
    for a in reversed(ch): o.update({c: dict(g) for c, g in grp.get(a, {}).items()})
    return o
leaves = [i for i, t in byt.items() if not t.get("children")]
before = {l: eff(l) for l in leaves}
n = 0
while True:
    conf = None
    for t in byt:
        for c in list(grp.get(t, {})):
            if any(c in grp.get(x, {}) for x in desc(t)): conf = (t, c); break
        if conf: break
    if not conf: break
    t, c = conf; g = grp[t].pop(c); n += 1
    for k in kids[t]:
        if c not in grp[k]: grp[k][c] = dict(g)
d["statements"] = [{"id": "statement:" + uuid.uuid4().hex, "taxon": t, "character": c,
                    "value": v, "frequency": f}
                   for t, gg in grp.items() for c, st in gg.items() for v, f in st.items()]
bad = [l for l in leaves if eff(l) != before[l]]
assert not bad, "effective values changed for %r" % [byt[b]["scientificName"] for b in bad]
json.dump(d, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{n} conflicts resolved -> {outp} ({len(d['statements'])} statements)")
