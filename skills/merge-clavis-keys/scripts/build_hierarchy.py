#!/usr/bin/env python3
"""Build the taxa tree for a merged key: root -> <rank> -> species, using the
rank chosen by choose_hierarchy.py, and hoist every group all species under one
parent share. Adds externalReference (taxonID) to each species.

NO OVERRIDING: a group is hoisted onto a parent only when EVERY descendant
agrees exactly, and it is removed from the children when hoisted. A node left
with a single child is collapsed. Whole frequency vectors move together.
Aborts unless every leaf's effective values are unchanged.

Usage: build_hierarchy.py IN.json OUT.json --root Soricidae --rank genus \
                          --cache species.csv.taxonomy-cache.json [--taxonomy nortaxa]

Name resolution goes through adapters/taxonomy/<name>.py (default: nortaxa,
or the CLAVIS_TAXONOMY environment variable).
"""
import argparse, json, collections, uuid, os
from _adapters import taxonomy

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("outp")
ap.add_argument("--root", required=True)
ap.add_argument("--rank", required=True, help="rank to group by, or 'flat' for none")
ap.add_argument("--cache", required=True)
ap.add_argument("--taxonomy", default=None, help="taxonomy adapter name (default: nortaxa)")
a = ap.parse_args()
tax = taxonomy(a.taxonomy)

d = json.load(open(a.inp, encoding="utf-8"))
cache = json.load(open(a.cache, encoding="utf-8")) if os.path.exists(a.cache) else {}

def rec(name):
    key = "REC:" + name
    if key in cache: return cache[key]
    cache[key] = tax.resolve(name)
    return cache[key]

species = [t for t in d["taxa"] if not t.get("children")]
K = lambda v: tuple(v) if isinstance(v, list) else v   # numerical [min, max] as a hashable key
grp = collections.defaultdict(dict)
for s in d["statements"]:
    grp[s["taxon"]].setdefault(s["character"], {})[K(s["value"])] = s["frequency"]
before = {t["id"]: {c: dict(g) for c, g in grp.get(t["id"], {}).items()} for t in species}

byrank = collections.defaultdict(list)
for t in species:
    r = rec(t["scientificName"])
    t["externalReference"] = {"serviceId": tax.SERVICE_ID, "externalId": str(r["taxonID"])}
    if a.rank == "flat":
        byrank[t["scientificName"]].append(t)   # every group single-child -> collapses
    else:
        byrank[r["higher"].get(a.rank) or t["scientificName"].split()[0]].append(t)
json.dump(cache, open(a.cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

groups = []
for gname in sorted(byrank):
    kids = sorted(byrank[gname], key=lambda t: t["scientificName"])
    groups.append({"id": "taxon:" + uuid.uuid4().hex, "scientificName": gname, "children": kids})
root = {"id": "taxon:" + uuid.uuid4().hex, "scientificName": a.root,
        "children": list(groups)}  # copy: groups is mutated below

# hoist: group -> its species; then root -> all groups
newgrp = {t["id"]: dict(before[t["id"]]) for t in species}
ggrp, rgrp = collections.defaultdict(dict), {}
for g in groups:
    ks = [t["id"] for t in g["children"]]
    for c in {c for k in ks for c in newgrp[k]}:
        vs = [newgrp[k].get(c) for k in ks]
        if all(v is not None for v in vs) and all(v == vs[0] for v in vs):
            ggrp[g["id"]][c] = vs[0]
            for k in ks: del newgrp[k][c]
for c in {c for g in groups for c in ggrp[g["id"]]}:
    vs = [ggrp[g["id"]].get(c) for g in groups]
    if all(v is not None for v in vs) and all(v == vs[0] for v in vs):
        rgrp[c] = vs[0]
        for g in groups: del ggrp[g["id"]][c]

# collapse single-child intermediate nodes (their group merges into the child)
collapsed = []
for g in list(groups):
    if len(g["children"]) == 1:
        kid = g["children"][0]
        for c, st in ggrp[g["id"]].items(): newgrp[kid["id"]][c] = st
        ggrp.pop(g["id"], None)
        groups.remove(g); root["children"].remove(g); root["children"].append(kid)
        collapsed.append(g["scientificName"])
root["children"].sort(key=lambda t: t["scientificName"])

out = []
def emit(tid, gg):
    for c, st in gg.items():
        for v, f in st.items():
            out.append({"id": "statement:" + uuid.uuid4().hex, "taxon": tid,
                        "character": c, "value": list(v) if isinstance(v, tuple) else v, "frequency": f})
emit(root["id"], rgrp)
for g in groups: emit(g["id"], ggrp[g["id"]])
for t in species: emit(t["id"], newgrp[t["id"]])
d["taxa"], d["statements"] = [root], out

par = {}
def w(ts, p=None):
    for t in ts: par[t["id"]] = p; w(t.get("children", []), t["id"])
w(d["taxa"])
g2 = collections.defaultdict(dict)
for s in out: g2[s["taxon"]].setdefault(s["character"], {})[K(s["value"])] = s["frequency"]
def eff(t):
    ch, x = [], t
    while x: ch.append(x); x = par[x]
    o = {}
    for anc in reversed(ch):
        for c, gg in g2.get(anc, {}).items(): o[c] = dict(gg)
    return o
bad = [t["scientificName"] for t in species if eff(t["id"]) != before[t["id"]]]
assert not bad, "effective values changed for %r" % bad
json.dump(d, open(a.outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{a.root} -> {len(groups)} {a.rank} nodes -> {len(species)} species; "
      f"{len(out)} statements ({len(rgrp)} groups on root, "
      f"{sum(len(v) for v in ggrp.values())} on {a.rank}, "
      f"{sum(len(v) for v in newgrp.values())} on species)")
if collapsed: print("collapsed single-child nodes:", ", ".join(collapsed))
print("effective values unchanged for all species")
