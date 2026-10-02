#!/usr/bin/env python3
"""Union-first merge, steps 5-6: collapse source-tagged characters into one
canonical set and reconcile their states.

Inputs
  union.json       from union_keys.py (characters titled "Trait [source]")
  concordance.json {"Canonical title": ["Trait [srcA]", "Other trait [srcB]"]}
  statemap.json    {"Canonical title": {"source state label": ["canonical label", ...]}}
                   a source label may map to SEVERAL canonical labels when the
                   source is vaguer than the canonical set; omit a label to
                   keep it unchanged.

Conflict policy, per (species, canonical character):
  * every source contributes the SET of canonical labels its statement allows
  * INTERSECTION FIRST -- if all sources' sets intersect, the intersection is
    the answer. A precise source narrows a vague one; that is not a conflict.
  * EMPTY INTERSECTION = real disagreement -- source-weighted frequencies:
    each source is one vote split evenly over the labels it allows, summed and
    normalized. Every value any source asserts stays reachable. (Majority rule
    was tried on the rodent key and destroyed 52 source claims.)
  * graded input frequencies are carried through as each source's weights
    rather than flattened to 1/len(set).

Usage: reconcile.py union.json concordance.json statemap.json out.json
"""
import json, sys, collections, uuid

union, conc, smap, outp = sys.argv[1:5]
d = json.load(open(union, encoding="utf-8"))
C = json.load(open(conc, encoding="utf-8"))
S = json.load(open(smap, encoding="utf-8"))
lang = "nb"

T = lambda o: next(iter(o["title"].values()))
char = {c["id"]: c for c in d["characters"]}
label = {s["id"]: T(s) for c in d["characters"] for s in (c.get("states") or [])}
src_of = {c["id"]: T(c).rsplit("[", 1)[-1].rstrip("]") for c in d["characters"]}

# A source character may feed MORE THAN ONE canonical axis -- that is how a
# bundled couplet character gets resolved late (e.g. a flank character that
# states both whether a pale side-zone exists AND how sharply it is bounded).
# When it does, every state must have an explicit statemap entry for each axis;
# a state with no entry for an axis simply says nothing about that axis.
tagged_to_canon = collections.defaultdict(list)
for canon, members in C.items():
    for m in members: tagged_to_canon[m].append(canon)
unmapped = [T(c) for c in d["characters"] if T(c) not in tagged_to_canon]
if unmapped:
    sys.exit("ERROR: characters missing from the concordance:\n  " + "\n  ".join(sorted(unmapped)))

# per (taxon, canonical char, source) -> {canonical label: freq}
acc = collections.defaultdict(lambda: collections.defaultdict(dict))
for st in d["statements"]:
    if st["frequency"] <= 0: continue
    tag = T(char[st["character"]])
    canons = tagged_to_canon[tag]
    src = src_of[st["character"]]
    raw = label[st["value"]]
    for canon in canons:
        m = S.get(canon, {})
        if raw in m:
            targets = m[raw]
        elif len(canons) > 1:
            continue          # says nothing about this axis
        else:
            targets = [raw]
        if isinstance(targets, str): targets = [targets]
        if not targets: continue
        for t in targets:
            g = acc[(st["taxon"], canon)][src]
            g[t] = g.get(t, 0.0) + st["frequency"] / len(targets)

final, conflicts = {}, []
for (tx, canon), bysrc in acc.items():
    sets = [set(g) for g in bysrc.values()]
    inter = set.intersection(*sets) if sets else set()
    if inter:
        # keep the graded shape of whichever sources are inside the intersection
        w = collections.Counter()
        for g in bysrc.values():
            tot = sum(v for k, v in g.items() if k in inter)
            if tot <= 0: continue
            for k, v in g.items():
                if k in inter: w[k] += v / tot
        s = sum(w.values()) or 1.0
        final[(tx, canon)] = {k: round(v / s, 4) for k, v in w.items()}
    else:
        w = collections.Counter()
        for g in bysrc.values():
            tot = sum(g.values()) or 1.0
            for k, v in g.items(): w[k] += (v / tot) / len(bysrc)
        s = sum(w.values()) or 1.0
        final[(tx, canon)] = {k: round(v / s, 4) for k, v in w.items()}
        conflicts.append((tx, canon, {k: sorted(v) for k, v in
                                      ((s_, set(g)) for s_, g in bysrc.items())}))

# emit
new_chars, cid, sid = [], {}, {}
for canon in sorted(C):
    labels = sorted({l for (tx, c), g in final.items() if c == canon for l in g})
    if not labels: continue
    c = {"id": "character:" + uuid.uuid4().hex, "title": {lang: canon},
         "type": "exclusive", "states": []}
    for l in labels:
        s = {"id": "state:" + uuid.uuid4().hex, "title": {lang: l}}
        sid[(canon, l)] = s["id"]; c["states"].append(s)
    cid[canon] = c["id"]; new_chars.append(c)

stmts = []
for (tx, canon), g in final.items():
    for l in [s["title"][lang] for s in next(c for c in new_chars if c["id"] == cid[canon])["states"]]:
        stmts.append({"id": "statement:" + uuid.uuid4().hex, "taxon": tx,
                      "character": cid[canon], "value": sid[(canon, l)],
                      "frequency": g.get(l, 0)})
d["characters"], d["statements"] = new_chars, stmts
json.dump(d, open(outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"{len(C)} canonical characters, {len(new_chars)} with data, {len(stmts)} statements")
print(f"real disagreements (empty intersection): {len(conflicts)}")
for tx, canon, bysrc in conflicts[:15]:
    print(f"  {canon}: " + " | ".join(f"{s}={v}" for s, v in bysrc.items()))
json.dump([{"taxon": t, "character": c, "sources": b} for t, c, b in conflicts],
          open(outp.replace(".json", "-conflicts.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
