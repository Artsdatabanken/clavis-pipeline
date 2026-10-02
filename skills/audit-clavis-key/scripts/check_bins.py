#!/usr/bin/env python3
"""Continuity check for quantitative state labels: reports gaps and overlaps
between adjacent bins in every character whose states parse as numeric ranges.

Convention (from the rodent key): "under X" / "over X-Y" / "over Y". The
single point X being uncovered is fine for a continuous measurement; an
overlap gives the user two valid answers and is a real defect.

Characters whose states are bare integers (exact counts like "3 | 4") are
atomic per-integer states -- skipped, not range bins.

Usage: check_bins.py KEY.json    (exit 1 if any gap/overlap found)
"""
import json, re, sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
L = lambda s: next(iter(s["title"].values()))
NUM = r"\d+(?:[.,]\d+)?"
def bounds(l):
    if re.match(rf"^(under|opptil|<)\s*{NUM}", l, re.I):
        return (0.0, float(re.search(NUM, l).group().replace(",", ".")))
    m = re.search(rf"({NUM})\s*[\u2013\u2012\u2014-]\s*({NUM})", l)  # X-Y range
    if m: return (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
    if re.match(rf"^(over|>)\s*{NUM}", l, re.I):
        return (float(re.search(NUM, l).group().replace(",", ".")), float("inf"))
    if re.fullmatch(rf"{NUM}( .*)?", l) and re.fullmatch(r"\d+", re.search(NUM, l).group()):
        return "int"  # exact count ("3", "4 par"): atomic state, not a bin
    return None  # descriptive label; character skipped
# Any unit of measure marks the quantity as continuous, where "under X / over X"
# is the required convention. Without a unit, integer bins are a discrete COUNT
# and the boundary value must belong to a bin.
UNIT = re.compile(r"(mm|cm|\bm\b|km|mg|\bg\b|kg|µm|%|sek|min|time[rn]?|døgn|"
                  r"dag(er)?|uke[rn]?|måned(er)?|år|\bs\b|gram|meter)", re.I)
bad = 0
# Numerical characters: unit, min <= max, each taxon range inside the character
# range. Overlap between taxa is normal (that is the data); a gap is not a defect.
units = {}
for c in d["characters"]:
    if c.get("type") != "numerical":
        continue
    t = next(iter(c["title"].values()))
    u = c.get("unit")
    if not u: print(f"NO-UNIT  {t}: numerical character without unit"); bad += 1
    units.setdefault(t.split("(")[0].strip().lower(), set()).add(json.dumps(u, sort_keys=True))
    if "min" in c and "max" in c and c["min"] > c["max"]:
        print(f"RANGE    {t}: min {c['min']} > max {c['max']}"); bad += 1
    for s in d["statements"]:
        if s["character"] != c["id"]: continue
        v = s["value"]
        if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)):
            print(f"VALUE    {t}: statement value {v!r} is not [min, max]"); bad += 1; continue
        if v[0] > v[1]: print(f"VALUE    {t}: lo > hi in {v}"); bad += 1
        if "min" in c and v[0] < c["min"] or "max" in c and v[1] > c["max"]:
            print(f"OUTSIDE  {t}: {v} outside character range [{c.get('min')}, {c.get('max')}]"); bad += 1
for c in d["characters"]:
    labs = [L(s) for s in (c.get("states") or [])]
    if not labs: continue
    bs = [bounds(l) for l in labs]
    if any(b is None or b == "int" for b in bs) or len(bs) < 2: continue
    bs.sort()
    t = next(iter(c["title"].values()))
    # A DISCRETE count (integer bounds, no unit of measure) is not a continuous
    # quantity: the boundary value is attainable, so "under 5 / over 5-8" leaves
    # a user who counted exactly 5 with no answer. For a continuous measurement
    # the same shape is the required convention -- an overlap would be worse.
    discrete = (not any(UNIT.search(l) for l in labs)
                and all(float(x).is_integer() for b in bs for x in b if x != float("inf")))
    for (a1, a2), (b1, b2) in zip(bs, bs[1:]):
        if b1 > a2: print(f"GAP      {t}: {a1:g}-{a2:g} then {b1:g}-{b2:g}"); bad += 1
        elif b1 < a2: print(f"OVERLAP  {t}: {a1:g}-{a2:g} vs {b1:g}-{b2:g}"); bad += 1
        elif discrete and b1 == a2:
            print(f"STRANDED {t}: discrete count -- the value {int(a2)} itself has no "
                  f"state ({a1:g}-{a2:g} then {b1:g}-{b2:g}). Relabel the bins so the "
                  f"boundary belongs to one of them."); bad += 1
print("clean" if not bad else f"{bad} defect(s)")
sys.exit(1 if bad else 0)
