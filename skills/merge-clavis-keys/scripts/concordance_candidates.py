#!/usr/bin/env python3
"""Pre-filter for the character concordance: which source characters in the
union probably describe the same observable? The agent decides only these
candidates, never all pairs.

Usage: concordance_candidates.py union.json --out candidates.md [--glossary glossary.json]

Signals per pair of source-tagged characters from DIFFERENT sources:
  * title similarity: token Jaccard on normalized titles (>= 0.4), or one title
    contained in the other
  * glossary: titles that normalize to the same entry in glossary.json
    ({"halelengde": ["svanslängd", "tail length"], ...})
  * numerical characters: same unit, and the per-taxon ranges overlap for most
    shared taxa
  * categorical: shared state labels (after normalization) for >= 2 states
  * data agreement over shared taxa, shown only as supporting evidence
Output: a markdown table grouped by the strongest signal, with the shared taxa
count and the state labels of each side, for the agent to accept into spec.json.
"""
import argparse, collections, itertools, json, re, unicodedata

ap = argparse.ArgumentParser()
ap.add_argument("union"); ap.add_argument("--out", required=True); ap.add_argument("--glossary")
a = ap.parse_args()
d = json.load(open(a.union, encoding="utf-8"))
T = lambda o: next(iter((o.get("title") or {}).values()), "")
def norm(s): return re.sub(r"[\s\-–—/,;:.()\[\]]+", " ", unicodedata.normalize("NFKC", s).lower()).strip()
STOP = {"i", "på", "av", "the", "of", "in", "and", "og", "eller", "or", "med", "with", "til", "to", "der", "die", "das", "van", "de"}
def toks(s): return {w for w in norm(s).split() if w not in STOP and len(w) > 2}
gl = {}
if a.glossary:
    for k, vs in json.load(open(a.glossary, encoding="utf-8")).items():
        for v in [k] + vs: gl[norm(v)] = norm(k)

chars = d["characters"]
src = {c["id"]: T(c).rsplit(" [", 1)[1].rstrip("]") for c in chars}
title = {c["id"]: T(c).rsplit(" [", 1)[0] for c in chars}
labels = {c["id"]: {norm(T(s)) for s in (c.get("states") or [])} for c in chars}
by_tc = collections.defaultdict(dict)
for s in d["statements"]:
    if s["frequency"] > 0:
        v = tuple(s["value"]) if isinstance(s["value"], list) else s["value"]
        by_tc[s["character"]].setdefault(s["taxon"], set()).add(v)
rows = []
for c1, c2 in itertools.combinations(chars, 2):
    if src[c1["id"]] == src[c2["id"]]: continue
    t1, t2 = title[c1["id"]], title[c2["id"]]
    sig = []
    j = len(toks(t1) & toks(t2)) / max(1, len(toks(t1) | toks(t2)))
    if j >= 0.4: sig.append(f"title {j:.2f}")
    elif norm(t1) in norm(t2) or norm(t2) in norm(t1): sig.append("title contained")
    if gl and gl.get(norm(t1)) and gl.get(norm(t1)) == gl.get(norm(t2)): sig.append("glossary")
    n1, n2 = c1.get("type") == "numerical", c2.get("type") == "numerical"
    shared = set(by_tc[c1["id"]]) & set(by_tc[c2["id"]])
    if n1 and n2 and c1.get("unit") == c2.get("unit") and shared:
        ov = sum(1 for t in shared if any(r1[0] <= r2[1] and r2[0] <= r1[1] for r1 in by_tc[c1["id"]][t] for r2 in by_tc[c2["id"]][t] if isinstance(r1, tuple) and isinstance(r2, tuple)))
        if ov >= max(1, len(shared) // 2): sig.append(f"ranges overlap {ov}/{len(shared)} ({c1.get('unit')})")
    if not n1 and not n2 and len(labels[c1["id"]] & labels[c2["id"]]) >= 2:
        sig.append(f"{len(labels[c1['id']] & labels[c2['id']])} shared labels")
    if not sig: continue
    agree = ""
    if shared and not n1 and not n2:
        sl = {s["id"]: norm(T(s)) for c in (c1, c2) for s in (c.get("states") or [])}
        same = sum(1 for t in shared if {sl.get(x, x) for x in by_tc[c1["id"]][t]} & {sl.get(x, x) for x in by_tc[c2["id"]][t]})
        agree = f"{same}/{len(shared)} taxa agree"
    rows.append((sig, t1, src[c1["id"]], t2, src[c2["id"]], len(shared), agree, sorted(labels[c1["id"]])[:6], sorted(labels[c2["id"]])[:6]))
rows.sort(key=lambda r: (-len(r[0]), r[1]))
out = ["# Concordance candidates\n", "Each row is a possible 'same observable' pair across sources. Accept into spec.json by meaning; the data column is evidence, not the trigger.\n",
       "| signals | character A | source | character B | source | shared taxa | data | states A | states B |", "|---|---|---|---|---|---|---|---|---|"]
for sig, t1, s1, t2, s2, n, ag, l1, l2 in rows:
    out.append(f"| {', '.join(sig)} | {t1} | {s1} | {t2} | {s2} | {n} | {ag} | {' / '.join(l1)} | {' / '.join(l2)} |")
open(a.out, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"{len(rows)} candidate pairs from {len(chars)} source-tagged characters -> {a.out}")
