#!/usr/bin/env python3
"""Zero-loss check: replay every source key's positive claims against the
merged key. Every claim must be SURVIVED (some value it asserts still has
frequency > 0), NARROWED (a more precise source cut it down), or DELIBERATELY
REMOVED (named in removed.json). Anything else is a silent loss and a defect.

Staleness was the recurring bug on the rodent key -- the checker carried its
own copies of the concordance and rename maps and drifted from the merge three
times, twice reporting false losses and once silently skipping renamed items
while appearing to pass. So this reads THE SAME FILES the merge used. Never
hand-copy a mapping in here; if a later step renames anything, it writes a
rename file and you pass it with --rename.

Usage:
  roundtrip.py --merged KEY.json --csv species.csv \
               --concordance concordance.json --statemap statemap.json \
               [--rename coarsening.json ...] [--removed removed.json] \
               SOURCE1.json SOURCE2.json ...
"""
import argparse, csv, json, collections, sys, os

ap = argparse.ArgumentParser()
ap.add_argument("sources", nargs="+")
ap.add_argument("--merged", required=True)
ap.add_argument("--csv", required=True)
ap.add_argument("--concordance", required=True)
ap.add_argument("--statemap", required=True)
ap.add_argument("--rename", action="append", default=[])
ap.add_argument("--removed", default=None)
a = ap.parse_args()

C = json.load(open(a.concordance, encoding="utf-8"))
S = json.load(open(a.statemap, encoding="utf-8"))
REN = {}
for r in a.rename:                      # {"Canonical char": {"old label": "new label"}}
    for c, m in json.load(open(r, encoding="utf-8")).items():
        REN.setdefault(c, {}).update(m)
REMOVED = set(json.load(open(a.removed, encoding="utf-8"))) if a.removed else set()
keep = {r["scientificName"].strip() for r in csv.DictReader(open(a.csv, encoding="utf-8-sig"))
        if r.get("scientificName", "").strip()}

tag2canon = {t: canon for canon, ms in C.items() for t in ms}

m = json.load(open(a.merged, encoding="utf-8"))
T = lambda o: next(iter(o["title"].values()))
mchar = {T(c): c for c in m["characters"]}
mlabel = {s["id"]: T(s) for c in m["characters"] for s in (c.get("states") or [])}
taxa, par = {}, {}
def walk(ts, p=None):
    for t in ts: taxa[t["id"]] = t; par[t["id"]] = p; walk(t.get("children", []), t["id"])
walk(m["taxa"])
byname = {t["scientificName"]: i for i, t in taxa.items() if not t.get("children")}
grp = collections.defaultdict(dict)
for s in m["statements"]:
    grp[s["taxon"]].setdefault(s["character"], {})[s["value"]] = s["frequency"]
def eff(t, cid):
    ch, x = [], t
    while x: ch.append(x); x = par[x]
    o = {}
    for anc in reversed(ch):
        if cid in grp.get(anc, {}): o.update(grp[anc][cid])
    return o

rows, losses = [], []
for path in a.sources:
    src = os.path.basename(path).split(".")[0]
    d = json.load(open(path, encoding="utf-8"))
    lg = lambda o: (o.get("title") or {}).get((d.get("language") or ["nb"])[0]) \
                   or next(iter((o.get("title") or {}).values()), "")
    st, pr = {}, {}
    def w2(ts, p=None):
        for t in ts: st[t["id"]] = t; pr[t["id"]] = p; w2(t.get("children", []), t["id"])
    w2(d["taxa"])
    ct = {c["id"]: lg(c) for c in d["characters"]}
    sl = {s["id"]: lg(s) for c in d["characters"] for s in (c.get("states") or [])}
    g2 = collections.defaultdict(dict)
    for s in d["statements"]:
        g2[s["taxon"]].setdefault(s["character"], {})[s["value"]] = s["frequency"]
    def eff2(t):
        ch, x = [], t
        while x: ch.append(x); x = par2(x)
        o = {}
        for anc in reversed(ch):
            for c, gg in g2.get(anc, {}).items(): o.setdefault(c, {}).update(gg)
        return o
    par2 = lambda x: pr[x]
    ok = nar = lost = skip = 0
    for leaf in [i for i, t in st.items() if not t.get("children")]:
        name = st[leaf]["scientificName"]
        if name not in keep or name not in byname: skip += 1; continue
        for cid, gg in eff2(leaf).items():
            pos = {sl[k] for k, v in gg.items() if v > 0}
            if not pos: continue
            canon = tag2canon.get(f"{ct[cid]} [{src}]") or tag2canon.get(ct[cid])
            if canon is None:
                if ct[cid] in REMOVED: continue
                skip += 1; continue
            if canon in REMOVED: continue
            cands = set()
            for p in pos:
                t2 = S.get(canon, {}).get(p, [p])
                cands.update([t2] if isinstance(t2, str) else t2)
            cands = {REN.get(canon, {}).get(x, x) for x in cands}
            mc = mchar.get(canon)
            if mc is None: lost += 1; losses.append((src, name, canon, sorted(cands), "character gone")); continue
            e = eff(byname[name], mc["id"])
            reachable = {mlabel[k] for k, v in e.items() if v > 0}
            if cands & reachable:
                ok += 1
                if not cands <= reachable: nar += 1
            else:
                lost += 1
                losses.append((src, name, canon, sorted(cands), f"all on 0; merged has {sorted(reachable)}"))
    rows.append((src, ok, nar, lost, skip))

print(f"{'source':<28}{'survived':>9}{'narrowed':>10}{'LOST':>6}{'skipped':>9}")
for r in rows: print(f"{r[0]:<28}{r[1]:>9}{r[2]:>10}{r[3]:>6}{r[4]:>9}")
tot = [sum(r[i] for r in rows) for i in (1, 2, 3, 4)]
print(f"\nSUM survived {tot[0]} | narrowed {tot[1]} | LOST {tot[2]} | skipped {tot[3]}")
for l in losses[:30]: print("  LOSS", l)
sys.exit(1 if tot[2] else 0)
