#!/usr/bin/env python3
"""Redundancy report for a Clavis key: which species pairs are separated, by
how many characters, and what each character contributes. Also tests proposed
state merges (coarsening): a merge is affordable when no pair loses its last
separating character, no pair with >=3 routes drops below 3, and the character
keeps >=75% of its own separating power.

Usage:
  redundancy.py KEY.json                    report
  redundancy.py KEY.json --merge PLAN.json  test a coarsening plan
                                            {"Char title": {"old state": "new label", ...}, ...}

Frequencies: a value counts as possible at ANY frequency > 0, so every number
here is a worst-case floor — frequency-ranking interfaces separate better.
"""
import json, sys, collections, itertools

def load(path):
    d = json.load(open(path, encoding="utf-8"))
    taxa, par = {}, {}
    def w(ts, p=None):
        for t in ts:
            taxa[t["id"]] = t; par[t["id"]] = p; w(t.get("children", []), t["id"])
    w(d["taxa"])
    leaves = [i for i, t in taxa.items() if not t.get("children")]
    byt = collections.defaultdict(dict)
    for s in d["statements"]:
        byt[s["taxon"]][(s["character"], s["value"])] = s["frequency"]
    def eff(t):
        c, x = [], t
        while x: c.append(x); x = par[x]
        v = {}
        for a in reversed(c): v.update(byt.get(a, {}))
        return v
    return d, leaves, {l: eff(l) for l in leaves}, taxa

T = lambda c: next(iter(c["title"].values()))
L = lambda s: next(iter(s["title"].values()))

def analyse(d, lv, E, M):
    grp = {}
    for c in d["characters"]:
        m = M.get(T(c), {})
        for s in c["states"]: grp[s["id"]] = m.get(L(s), L(s))
    POS, conf, tot = {}, 0, 0
    for l in lv:
        mm = collections.defaultdict(set)
        for (c, s), f in E[l].items():
            if f > 0: mm[c].add(grp[s])
        POS[l] = mm
        for v in mm.values():
            tot += 1; conf += (len(v) == 1)
    sep = collections.defaultdict(set); pc = collections.Counter()
    cids = [c["id"] for c in d["characters"]]
    for a, b in itertools.combinations(lv, 2):
        for c in cids:
            A, B = POS[a].get(c), POS[b].get(c)
            if A and B and not (A & B): sep[(a, b)].add(c); pc[c] += 1
    return sep, conf, tot, pc

if __name__ == "__main__":
    d, lv, E, taxa = load(sys.argv[1])
    sep, conf, tot, pc = analyse(d, lv, E, {})
    npairs = len(list(itertools.combinations(lv, 2)))
    if "--merge" in sys.argv:
        M = json.load(open(sys.argv[sys.argv.index("--merge") + 1], encoding="utf-8"))
        # rewrite plan {"char":{"old":"new"}} so merged states share one label
        sep2, conf2, tot2, pc2 = analyse(d, lv, E, M)
        lost = [k for k in sep if k not in sep2]
        weak = [k for k in sep if k in sep2 and len(sep[k]) >= 3 and len(sep2[k]) < 3]
        drained = [T(c) for c in d["characters"]
                   if T(c) in M and pc2[c["id"]] < 0.75 * pc[c["id"]]]
        ok = not lost and not weak and not drained
        print(f"pairs lost: {len(lost)} | pairs dropping below 3 routes: {len(weak)} | "
              f"characters losing >25% own power: {drained or 'none'}")
        print(f"confident cells {conf}/{tot} -> {conf2}/{tot2}")
        print("AFFORDABLE" if ok else "NOT AFFORDABLE")
        sys.exit(0 if ok else 1)
    dist = collections.Counter(len(v) for v in sep.values())
    med = sorted(len(v) for v in sep.values())[len(sep) // 2] if sep else 0
    print(f"{len(lv)} leaves, {npairs} pairs; separated: {len(sep)}; median routes {med}")
    print(f"confident cells: {conf}/{tot} ({100*conf/tot:.0f}%)")
    print("routes histogram:", dict(sorted(dist.items())))
    un = [k for k in itertools.combinations(lv, 2) if k not in sep]
    for a, b in un: print("  INSEPARABLE:", taxa[a]["scientificName"], "/", taxa[b]["scientificName"])
    print("\nper-character pairs separated:")
    for c in sorted(d["characters"], key=lambda c: -pc[c["id"]]):
        print(f"  {pc[c['id']]:4d}  {T(c)}")
