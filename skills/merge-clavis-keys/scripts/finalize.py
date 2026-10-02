#!/usr/bin/env python3
"""Final presentation pass on a merged key:
  1. drop characters no answer can ever rule a taxon out with: only one taxon
     is scored and every other taxon is unknown. A trait that other taxa are
     scored as lacking (round tail vs flat tail) separates and stays. Names
     written to removed.json. Rule from Wouter, 2026-10-02: a trait one species
     has and others don't is valid; it is useless only when the others are
     unknown.
  2. order each character's states meaningfully: numeric bins ascending by
     lower bound, months chronologically, everything else left as authored
     (alphabetical order on a measurement character is unreadable)
  3. order characters by field-answerability using an explicit tier list

Usage: finalize.py IN.json OUT.json --removed removed.json [--order order.json]
       order.json = {"tiers": [["Char title", ...], ...]}  first tier first
"""
import argparse, json, re, collections, itertools, sys

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("outp")
ap.add_argument("--removed", required=True)
ap.add_argument("--order", default=None)
a = ap.parse_args()
d = json.load(open(a.inp, encoding="utf-8"))
T = lambda o: next(iter(o["title"].values()))

taxa, par = {}, {}
def w(ts, p=None):
    for t in ts: taxa[t["id"]] = t; par[t["id"]] = p; w(t.get("children", []), t["id"])
w(d["taxa"])
leaves = [i for i, t in taxa.items() if not t.get("children")]
g = collections.defaultdict(dict)
for s in d["statements"]:
    v = tuple(s["value"]) if isinstance(s["value"], list) else s["value"]   # numerical [min, max]
    g[s["taxon"]].setdefault(s["character"], {})[v] = s["frequency"]
def eff(t):
    ch, x = [], t
    while x: ch.append(x); x = par[x]
    o = {}
    for anc in reversed(ch):
        for c, gg in g.get(anc, {}).items(): o[c] = dict(gg)
    return o
E = {l: eff(l) for l in leaves}
pos = {l: {c: {v for v, f in gg.items() if f > 0} for c, gg in E[l].items()} for l in leaves}
power = collections.Counter()
for x, y in itertools.combinations(leaves, 2):
    for c in {cc["id"] for cc in d["characters"]}:
        A, B = pos[x].get(c), pos[y].get(c)
        if not (A and B): continue
        if all(isinstance(v, tuple) for v in A | B):   # numerical: separated when no ranges overlap
            if not any(p[0] <= q[1] and q[0] <= p[1] for p in A for q in B): power[c] += 1
        elif not (A & B): power[c] += 1
dead = [c for c in d["characters"] if power[c["id"]] == 0]
json.dump([T(c) for c in dead], open(a.removed, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
deadids = {c["id"] for c in dead}
d["characters"] = [c for c in d["characters"] if c["id"] not in deadids]
d["statements"] = [s for s in d["statements"] if s["character"] not in deadids]

NUM = r"\d+(?:[.,]\d+)?"
def lower(l):
    """Sort key for a state label that starts with a number or a comparison symbol;
    None for word labels (left in authored order). No words of any language."""
    s = l.strip()
    m = re.match(rf"^[<≤]\s*({NUM})", s)
    if m: return -1e18
    m = re.match(rf"^({NUM})\s*[–—-]\s*({NUM})", s)
    if m: return float(m.group(1).replace(",", "."))
    m = re.match(rf"^[>≥]?\s*({NUM})", s)
    if m: return float(m.group(1).replace(",", "."))
    return None
for c in d["characters"]:
    if not c.get("states"): continue   # numerical characters have no states
    labs = [T(s) for s in c["states"]]
    if all(lower(l) is not None for l in labs):
        c["states"].sort(key=lambda s: lower(T(s)))

if a.order:
    tiers = json.load(open(a.order, encoding="utf-8"))["tiers"]
    # Rank by exact position in the flattened tier list -- ranking by tier
    # index alone keeps the tiers but leaves each tier alphabetical, losing
    # the deliberate within-tier order (ground colour before boundary detail).
    flat = [t for tier in tiers for t in tier]
    rank = {t: i for i, t in enumerate(flat)}
    missing = [T(c) for c in d["characters"] if T(c) not in rank]
    if missing: sys.exit("ERROR: characters missing from the order tiers:\n  " + "\n  ".join(missing))
    d["characters"].sort(key=lambda c: rank[T(c)])

json.dump(d, open(a.outp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"removed {len(dead)} zero-power characters: {', '.join(T(c) for c in dead) or 'none'}")
print(f"{len(d['characters'])} characters, {len(d['statements'])} statements -> {a.outp}")
