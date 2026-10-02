#!/usr/bin/env python3
"""Zero-loss check: replay every source key's positive claims against the
merged key. Reads THE SAME files the merge used (spec.json, the rename chain,
removed.json); never a hand-copied mapping.

Usage:
  roundtrip.py --merged KEY.json --spec spec.json --csv species.csv [--alias alias.json]
               [--rename R1.json --rename R2.json ...] [--removed removed.json] [--report out.md]
               SOURCE1.json SOURCE2.json ...

Claim = (source, species, source character, canonical axis). Outcomes:
  survived   exclusive: some asserted value still has frequency > 0;
             non-exclusive: EVERY asserted state still > 0;
             numerical: the merged range contains the source range
  narrowed   survived, but not every asserted value is still reachable
             (a more precise source cut it), or a threshold range of a
             {"bound": true} member gave way to measurements it overlaps;
             counted inside survived
  removed    the canonical character, or this species' statements on it, are
             listed in removed.json (deliberate); format either a list of
             titles or {title: {"species": "all" | [names]}}
  LOST       anything else, including a source character absent from spec
             and a label that maps to nothing on every axis (UNREPRESENTED)
Renames ({"Canonical": {"old label": "new label"}, "__characters__": {"old
title": "new title"}}) are chained in the order given; a label renamed to
"[lo, hi]" on a character that is now numerical (bins converted by the
determinability pass) survives when the range lies inside the merged range.
Exit 1 on any loss.
"""
import argparse, collections, csv, json, os, sys

ap = argparse.ArgumentParser()
ap.add_argument("sources", nargs="+")
ap.add_argument("--merged", required=True); ap.add_argument("--spec", required=True)
ap.add_argument("--csv", required=True); ap.add_argument("--alias")
ap.add_argument("--rename", action="append", default=[]); ap.add_argument("--removed")
ap.add_argument("--report")
a = ap.parse_args()

load = lambda p: json.load(open(p, encoding="utf-8"))
T = lambda o: next(iter((o.get("title") or {}).values()), "")
spec = load(a.spec)
alias = {k: (v[0] if isinstance(v, list) else v) for k, v in load(a.alias).items()} if a.alias else {}
keep = {r["scientificName"].strip() for r in csv.DictReader(open(a.csv, encoding="utf-8-sig")) if r.get("scientificName", "").strip()}
removed = {}
if a.removed:
    r = load(a.removed)
    removed = {k: "all" for k in r} if isinstance(r, list) else {k: (v.get("species", "all") if isinstance(v, dict) else "all") for k, v in r.items()}
def is_removed(canon, sp):
    v = removed.get(canon); return v is not None and (v == "all" or sp in v)
chain = [load(p) for p in a.rename]
def ren(canon, lab):
    for m in chain: lab = m.get(canon, {}).get(lab, lab)
    return lab
def renc(canon):
    for m in chain: canon = m.get("__characters__", {}).get(canon, canon)
    return canon

def tree(d):
    taxa, par = {}, {}
    def w(ts, p=None):
        for t in ts: taxa[t["id"]] = t; par[t["id"]] = p; w(t.get("children", []), t["id"])
    w(d["taxa"]); return taxa, par, [i for i, t in taxa.items() if not t.get("children")]
def effective(d):
    taxa, par, leaves = tree(d)
    g = collections.defaultdict(dict)
    for s in d["statements"]:
        v = tuple(s["value"]) if isinstance(s["value"], list) else s["value"]
        g[s["taxon"]].setdefault(s["character"], {})[v] = s["frequency"]
    out = {}
    for l in leaves:
        ch, x = [], l
        while x: ch.append(x); x = par[x]
        o = {}
        for anc in reversed(ch):
            for c, gg in g.get(anc, {}).items(): o.setdefault(c, {}).update(gg)
        out[l] = o
    return out

m = load(a.merged)
mtaxa, mpar, mleaves = tree(m); mE = effective(m)
mchar = {T(c): c for c in m["characters"]}
mlab = {s["id"]: T(s) for c in m["characters"] for s in (c.get("states") or [])}
byname = {mtaxa[l]["scientificName"]: l for l in mleaves}
feeds = collections.defaultdict(list)
for canon, v in spec.items():
    for s, mm in v.get("members", {}).items():
        for t in mm: feeds[(s, t)].append(canon)

rows, losses = [], []
for path in a.sources:
    src = os.path.basename(path).split(".")[0]
    d = load(path)
    taxa, par, leaves = tree(d); E = effective(d)
    ct = {c["id"]: T(c) for c in d["characters"]}
    sl = {s["id"]: T(s) for c in d["characters"] for s in (c.get("states") or [])}
    n = collections.Counter()
    for leaf in leaves:
        name = alias.get(taxa[leaf]["scientificName"], taxa[leaf]["scientificName"])
        if name not in keep: n["out_of_scope"] += 1; continue
        if name not in byname: n["LOST"] += 1; losses.append((src, name, "*", "species missing from merged key")); continue
        for cid, g in E[leaf].items():
            pos = [(k, v) for k, v in g.items() if v > 0]
            if not pos: continue
            title = ct[cid]
            if (src, title) not in feeds:
                n["LOST"] += 1; losses.append((src, name, title, "source character not in spec")); continue
            said = False
            for canon in feeds[(src, title)]:
                v = spec[canon]
                mc = mchar.get(renc(canon))
                if v["type"] == "numerical":
                    said = True
                    if is_removed(canon, name): n["removed"] += 1; continue
                    if mc is None: n["LOST"] += 1; losses.append((src, name, canon, "character gone, not in removed.json")); continue
                    e = mE[byname[name]].get(mc["id"], {})
                    rng = [k for k in e if isinstance(k, tuple)]
                    src_r = [k for k, _ in pos if isinstance(k, tuple)]
                    if not rng or not src_r: n["LOST"] += 1; losses.append((src, name, canon, "no range in merged key")); continue
                    lo, hi = min(r[0] for r in rng), max(r[1] for r in rng)
                    mm = v["members"][src][title] or {}
                    f = mm.get("scale", 1)
                    sc = next(c for c in d["characters"] if c["id"] == cid)
                    slo, shi = min(r[0] for r in src_r), max(r[1] for r in src_r)
                    bnd = bool(mm.get("bound")) and (slo <= sc.get("min", float("-inf")) or shi >= sc.get("max", float("inf")))
                    slo, shi = slo * f, shi * f
                    if lo <= slo and shi <= hi: n["survived"] += 1
                    elif bnd and lo <= shi and slo <= hi: n["survived"] += 1; n["narrowed"] += 1
                    else: n["LOST"] += 1; losses.append((src, name, canon, f"source range [{slo}, {shi}] not inside merged [{lo}, {hi}]"))
                    continue
                mp = v["members"][src][title]
                per_label = {sl.get(k, k): mp.get(sl.get(k, k), []) for k, _ in pos}
                per_label = {k: t for k, t in per_label.items() if t}
                if not per_label: continue
                said = True
                if is_removed(canon, name): n["removed"] += 1; continue
                if mc is None: n["LOST"] += 1; losses.append((src, name, canon, "character gone, not in removed.json")); continue
                e = mE[byname[name]].get(mc["id"], {})
                reach = {mlab[k] for k, f in e.items() if f > 0 and k in mlab}
                need = {ren(canon, t) for tg in per_label.values() for t in tg}
                if mc.get("type") == "numerical":   # bins converted to a numerical character; renames map labels to "[lo, hi]"
                    rng = [k for k in e if isinstance(k, tuple)]
                    try: want = [tuple(json.loads(x)) for x in need]
                    except (ValueError, TypeError): want = []
                    inside = [min(r[0] for r in rng) <= w[0] and w[1] <= max(r[1] for r in rng) for w in want] if rng else []
                    if inside and (all(inside) if v["type"] == "non-exclusive" else any(inside)):   # exclusive: one surviving value suffices, as for labels
                        n["survived"] += 1
                        if not all(inside): n["narrowed"] += 1
                    else: n["LOST"] += 1; losses.append((src, name, canon, f"bins {sorted(need)} not inside merged ranges {sorted(rng)}"))
                    continue
                if v["type"] == "non-exclusive":
                    if need <= reach: n["survived"] += 1
                    else: n["LOST"] += 1; losses.append((src, name, canon, f"states {sorted(need - reach)} gone; merged has {sorted(reach)}"))
                else:
                    if need & reach:
                        n["survived"] += 1
                        if not need <= reach: n["narrowed"] += 1
                    else: n["LOST"] += 1; losses.append((src, name, canon, f"asserted {sorted(need)}; merged has {sorted(reach)}"))
            if not said:
                n["LOST"] += 1; losses.append((src, name, title, f"UNREPRESENTED: {[sl.get(k, k) for k, _ in pos]} map to nothing on any axis"))
    rows.append((src, n))

out = [f"{'source':<14}{'survived':>9}{'(narrowed)':>11}{'removed':>9}{'LOST':>6}  out of scope"]
tot = collections.Counter()
for src, n in rows:
    out.append(f"{src:<14}{n['survived']:>9}{n['narrowed']:>11}{n['removed']:>9}{n['LOST']:>6}  {n['out_of_scope']}"); tot.update(n)
out.append(f"{'SUM':<14}{tot['survived']:>9}{tot['narrowed']:>11}{tot['removed']:>9}{tot['LOST']:>6}  {tot['out_of_scope']}")
for l in losses: out.append("  LOSS " + " | ".join(map(str, l)))
print("\n".join(out))
if a.report:
    open(a.report, "w", encoding="utf-8").write("```\n" + "\n".join(out) + "\n```\n")
sys.exit(1 if tot["LOST"] else 0)
