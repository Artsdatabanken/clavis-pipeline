#!/usr/bin/env python3
"""Union-first merge, steps 5-6: collapse source-tagged characters into one
canonical set and reconcile their values, driven by one spec file.

Usage: reconcile.py union.json spec.json out.json [--lang nb]

spec.json (the concordance and the state maps in one place, written by the
merge agent; maps are per source character because the same label can mean
different things in different source characters):
{
  "Canonical title": {
    "type": "exclusive" | "non-exclusive" | "numerical",
    "unit": "mm",                                  # numerical only
    "states": ["label a", "label b", ...],         # canonical order; categorical only
    "members": {
      "<source tag>": {
        "<source character title>": {              # as titled in the source key
          "<source state label>": ["label a"],     # one or more canonical labels; [] = says nothing
          ...                                      # numerical members: {} (ranges pass through),
                                                   # or {"scale": 10} when the source unit differs
                                                   # (cm -> mm); ranges are multiplied by scale.
                                                   # {"bound": true}: the source's ranges that touch
                                                   # its character's min or max are key thresholds
                                                   # ("shorter than 30 cm", open end closed at a chosen
                                                   # limit), not measurements: they give way to the
                                                   # measured ranges they overlap, and stand only
                                                   # where nothing was measured or they disagree
        }
      }
    }
  }
}

Policy, per (taxon, canonical character):
  * EXCLUSIVE: each source contributes the set of canonical labels its
    statements allow. If one source feeds the axis through several of its own
    characters, those are intersected first so the source casts one vote.
    Intersection across sources first (a precise source narrows a vague one;
    counted as narrowed, not lost). Empty intersection = real disagreement:
    every asserted label stays reachable. No vote shares: a label's frequency
    is the highest any source gives it, and the most likely label is 1.
    Frequencies are weak priors (see harvest-claims/references/frequency-table.json).
  * NON-EXCLUSIVE: each state is its own claim; union of asserted states,
    frequency = highest any source gives it. No intersection, no rescaling.
  * NUMERICAL: union of ranges per taxon across sources (lowest min, highest
    max); the character's min/max become the extremes over all taxa. No bins.

Writes out.json, out-conflicts.json (real disagreements, for the decisions
document) and out-intrasource.json (one source disagreeing with itself).
"""
import argparse, collections, json, sys, uuid

ap = argparse.ArgumentParser()
ap.add_argument("union"); ap.add_argument("spec"); ap.add_argument("out")
ap.add_argument("--lang", default=None)
a = ap.parse_args()
d = json.load(open(a.union, encoding="utf-8"))
spec = json.load(open(a.spec, encoding="utf-8"))
lang = a.lang or (d.get("language") or ["nb"])[0]

T = lambda o: next(iter((o.get("title") or {}).values()), "")
char = {c["id"]: c for c in d["characters"]}
label = {s["id"]: T(s) for c in d["characters"] for s in (c.get("states") or [])}
def split_tag(c):
    t = T(c)
    if " [" not in t: sys.exit(f"ERROR: union character without source tag: {t}")
    title, src = t.rsplit(" [", 1); return src.rstrip("]"), title
tag = {cid: split_tag(c) for cid, c in char.items()}

feeds = collections.defaultdict(list)          # (src, title) -> [canon]
for canon, v in spec.items():
    for s, m in v.get("members", {}).items():
        for t in m: feeds[(s, t)].append(canon)
missing = sorted(set(tag[c] for c in char if tag[c] not in feeds))
if missing:
    sys.exit("ERROR: union characters missing from spec:\n  " + "\n  ".join(f"{s}: {t}" for s, t in missing))

acc = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(dict)))  # (taxon, canon) -> src -> title -> {label: f}
num = collections.defaultdict(list)                                                                     # (taxon, canon) -> [(lo, hi, src)]
for st in d["statements"]:
    if st["frequency"] <= 0: continue
    src, title = tag[st["character"]]
    for canon in feeds[(src, title)]:
        v = spec[canon]
        if v["type"] == "numerical":
            if isinstance(st["value"], list) and len(st["value"]) == 2:
                mm = v["members"][src][title] or {}
                f = mm.get("scale", 1)
                sc = char[st["character"]]
                bnd = bool(mm.get("bound")) and (st["value"][0] <= sc.get("min", float("-inf")) or st["value"][1] >= sc.get("max", float("inf")))
                num[(st["taxon"], canon)].append((st["value"][0] * f, st["value"][1] * f, src, bnd))
            else:
                sys.exit(f"ERROR: {canon}: source {src} '{title}' is mapped as numerical but carries state values; convert its bins to ranges first")
            continue
        raw = label.get(st["value"], st["value"])
        m = v["members"][src][title]
        if raw not in m:
            sys.exit(f"ERROR: {canon}: no mapping for label {raw!r} of {src} '{title}'")
        tg = m[raw]
        if not tg: continue
        u = acc[(st["taxon"], canon)][src].setdefault(title, {})
        for t in tg: u[t] = max(u.get(t, 0.0), st["frequency"])

final, conflicts, narrowed, intra = {}, [], [], []
for key, rs in list(num.items()):          # thresholds give way to overlapping measurements
    meas = [r for r in rs if not r[3]]
    if not meas or len(meas) == len(rs): continue
    lo, hi = min(r[0] for r in meas), max(r[1] for r in meas)
    if all(r[0] <= hi and lo <= r[1] for r in rs if r[3]):
        num[key] = meas; narrowed.append(key)
for (tx, canon), bysrc in acc.items():
    typ = spec[canon]["type"]
    if typ == "non-exclusive":
        w = {}
        for units in bysrc.values():
            for u in units.values():
                for k, v in u.items(): w[k] = max(w.get(k, 0.0), v)
        final[(tx, canon)] = {k: round(v, 4) for k, v in w.items()}
        continue
    per = {}
    for s, units in bysrc.items():
        us = [u for u in units.values() if u]
        if not us: continue
        if len(us) == 1: per[s] = dict(us[0]); continue
        inter = set.intersection(*[set(u) for u in us])
        if not inter: intra.append((tx, canon, s, [sorted(u) for u in us]))
        keep = inter if inter else set().union(*[set(u) for u in us])
        g = {}
        for u in us:
            for k, v in u.items():
                if k in keep: g[k] = max(g.get(k, 0.0), v)
        per[s] = g
    sets = [set(g) for g in per.values()]
    inter = set.intersection(*sets) if sets else set()
    if inter:
        w = {k: max(g.get(k, 0.0) for g in per.values()) for k in inter}
        if any(not s <= inter for s in sets): narrowed.append((tx, canon))
    else:
        w = {}
        for g in per.values():
            for k, v in g.items(): w[k] = max(w.get(k, 0.0), v)
        conflicts.append((tx, canon, {s: sorted(g) for s, g in per.items()}))
    top = max(w.values()) if w else 1.0
    final[(tx, canon)] = {k: (1 if v == top else round(v, 4)) for k, v in w.items()}

new_chars, cid, sid = [], {}, {}
for canon, v in spec.items():
    c = {"id": "character:" + uuid.uuid4().hex, "title": {lang: canon}, "type": v["type"]}
    if v["type"] == "numerical":
        rs = [r for (tx, cn), lst in num.items() if cn == canon for r in lst]
        if not rs: continue
        c["unit"] = v.get("unit", ""); c["stepSize"] = v.get("stepSize", 1)
        c["min"] = min(r[0] for r in rs); c["max"] = max(r[1] for r in rs)
        cid[canon] = c["id"]; new_chars.append(c); continue
    used = {l for (tx, cn), g in final.items() if cn == canon for l in g}
    labels = [l for l in v.get("states", []) if l in used] + sorted(used - set(v.get("states", [])))
    if not labels: continue
    c["states"] = []
    for l in labels:
        s = {"id": "state:" + uuid.uuid4().hex, "title": {lang: l}}
        sid[(canon, l)] = s["id"]; c["states"].append(s)
    cid[canon] = c["id"]; new_chars.append(c)

stmts = []
for (tx, canon), g in final.items():
    if canon not in cid: continue
    for l, f in g.items():
        stmts.append({"id": "statement:" + uuid.uuid4().hex, "taxon": tx, "character": cid[canon], "value": sid[(canon, l)], "frequency": f})
for (tx, canon), rs in num.items():
    if canon not in cid: continue
    stmts.append({"id": "statement:" + uuid.uuid4().hex, "taxon": tx, "character": cid[canon],
                  "value": [min(r[0] for r in rs), max(r[1] for r in rs)], "frequency": 1})
d["characters"], d["statements"] = new_chars, stmts
d["language"] = [lang]
json.dump(d, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
names = {t["id"]: t.get("scientificName", t["id"]) for t in d["taxa"]}
print(f"{len(spec)} canonical characters, {len(new_chars)} with data ({sum(1 for c in new_chars if c['type'] == 'numerical')} numerical), {len(stmts)} statements")
print(f"narrowed groups (a precise source cut a vague one): {len(narrowed)}")
print(f"real disagreements (empty intersection, all values kept): {len(conflicts)}")
print(f"within-source disagreements: {len(intra)}")
base = a.out[:-5] if a.out.endswith(".json") else a.out
json.dump([{"taxon": names.get(t, t), "character": c, "sources": b} for t, c, b in conflicts], open(base + "-conflicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump([{"taxon": names.get(t, t), "character": c, "source": s, "sets": u} for t, c, s, u in intra], open(base + "-intrasource.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
