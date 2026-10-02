#!/usr/bin/env python3
"""Union-first merge, steps 1-3: trim to the species list, namespace every id,
concatenate, and merge taxa by accepted name.

Union has no order, so every source weighs the same -- this is what makes
"equal weight per source" structural instead of a tallying rule.

Characters stay SOURCE-TAGGED here (title + " [src]"), which is what makes the
taxon merge lossless: each species simply carries all sources' statements side
by side until the character concordance runs.

Usage:
  union_keys.py --csv species.csv --out union.json KEY1.json KEY2.json ...
  optional: --alias alias.json   {"Source name": ["Accepted name", "evidence"]}

Dead-character rule after trimming: a character is dropped ONLY if every leaf
is answered AND they all give the identical answer set. "All answered taxa
agree" is NOT enough -- a character answered for two of seven taxa can still be
the thing that identifies one of them.
"""
import argparse, csv, json, collections, uuid, sys, os

ap = argparse.ArgumentParser()
ap.add_argument("keys", nargs="+")
ap.add_argument("--csv", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--alias", default=None)
a = ap.parse_args()

keep_names = {r["scientificName"].strip()
              for r in csv.DictReader(open(a.csv, encoding="utf-8-sig"))
              if r.get("scientificName", "").strip()}
alias = {}
if a.alias:
    alias = {k: v[0] if isinstance(v, list) else v
             for k, v in json.load(open(a.alias, encoding="utf-8")).items()}

def accept(n): return alias.get(n, n)

# Two versions of the same source (key.json and key.v2.json) would silently
# count that source twice and break equal weighting -- the one thing the
# union-first design exists to guarantee. Refuse rather than warn.
srcs = collections.Counter(os.path.basename(p).split(".")[0] for p in a.keys)
dupes = {s: n for s, n in srcs.items() if n > 1}
if dupes:
    sys.exit("ERROR: same source given more than once (equal weighting would break): "
             + ", ".join(f"{s} x{n}" for s, n in dupes.items())
             + "\nPass exactly one file per source -- e.g. only the audited .v2.json.")

out = {"taxa": [], "characters": [], "statements": []}
by_species = {}            # accepted name -> taxon dict in the union
report = []

for path in a.keys:
    src = os.path.basename(path).split(".")[0]
    d = json.load(open(path, encoding="utf-8"))
    lang = (d.get("language") or ["und"])[0]
    T = lambda o: (o.get("title") or {}).get(lang) or next(iter((o.get("title") or {}).values()), "")

    taxa, par = {}, {}
    def walk(ts, p=None):
        for t in ts:
            taxa[t["id"]] = t; par[t["id"]] = p; walk(t.get("children", []), t["id"])
    walk(d["taxa"])
    leaves = [i for i, t in taxa.items() if not t.get("children")]

    grp = collections.defaultdict(dict)
    for s in d["statements"]:
        v = tuple(s["value"]) if isinstance(s["value"], list) else s["value"]
        grp[s["taxon"]].setdefault(s["character"], {})[v] = s["frequency"]
    def eff(t):                       # inherit downward; no overriding in Clavis
        ch, x = [], t
        while x: ch.append(x); x = par[x]
        o = {}
        for anc in reversed(ch):
            for c, g in grp.get(anc, {}).items(): o.setdefault(c, {}).update(g)
        return o

    kept_leaves = [l for l in leaves if accept(taxa[l]["scientificName"]) in keep_names]
    dropped = [taxa[l]["scientificName"] for l in leaves if l not in kept_leaves]

    eff_of = {l: eff(l) for l in kept_leaves}
    state_label, char_of_state = {}, {}
    for c in d["characters"]:
        for s in (c.get("states") or []):
            state_label[s["id"]] = T(s); char_of_state[s["id"]] = c["id"]

    # dead characters: all leaves answered and identical
    asserted = collections.defaultdict(dict)
    for l in kept_leaves:
        for c, g in eff_of[l].items():
            pos = frozenset(k for k, v in g.items() if v > 0)
            if pos: asserted[c][l] = frozenset(state_label.get(x, x) for x in pos)
    dead = set()
    for c in d["characters"]:
        aa = asserted.get(c["id"], {})
        if not aa: dead.add(c["id"])
        elif len(aa) == len(kept_leaves) and len(set(aa.values())) < 2: dead.add(c["id"])

    idmap = {}
    for c in d["characters"]:
        if c["id"] in dead: continue
        nc = json.loads(json.dumps(c))
        nc["id"] = "character:" + uuid.uuid4().hex
        nc["title"] = {lang: f"{T(c)} [{src}]"}
        idmap[c["id"]] = nc["id"]
        for s in (nc.get("states") or []):
            old = s["id"]; s["id"] = "state:" + uuid.uuid4().hex; idmap[old] = s["id"]
        out["characters"].append(nc)

    for l in kept_leaves:
        name = accept(taxa[l]["scientificName"])
        if name not in by_species:
            by_species[name] = {"id": "taxon:" + uuid.uuid4().hex, "scientificName": name}
        tid = by_species[name]["id"]
        for c, g in eff_of[l].items():
            if c in dead: continue
            for v, f in g.items():
                out["statements"].append({"id": "statement:" + uuid.uuid4().hex,
                                          "taxon": tid, "character": idmap[c],
                                          "value": list(v) if isinstance(v, tuple) else idmap[v], "frequency": f})
    report.append((src, len(kept_leaves), len(d["characters"]) - len(dead), len(dead), dropped))

out["taxa"] = [by_species[n] for n in sorted(by_species)]
json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"{'source':<28}{'species':>8}{'chars':>7}{'dead':>6}  out-of-scope taxa dropped")
for src, nl, nc, nd, dr in report:
    print(f"{src:<28}{nl:>8}{nc:>7}{nd:>6}  {len(dr)}")
print(f"\nunion: {len(out['taxa'])} species, {len(out['characters'])} source-tagged "
      f"characters, {len(out['statements'])} statements -> {a.out}")
missing = keep_names - set(by_species)
if missing: print("NOT COVERED BY ANY SOURCE:", ", ".join(sorted(missing)))
