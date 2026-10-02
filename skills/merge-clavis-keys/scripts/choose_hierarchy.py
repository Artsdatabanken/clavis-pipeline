#!/usr/bin/env python3
"""Decide which taxonomic ranks the key's hierarchy should keep -- from the
data, not by asking. Walking ranks from the root down, a rank is kept only if:

  1. COMPLETE   every species has an ancestor at that rank
  2. IT GROUPS  at least 2 and at most n/2 groups (a rank with nearly one group
                per species groups nothing; one group is the root again)

Grouping exists to keep the list scannable, so first ask whether any grouping
is needed at all: with FLAT_MAX (16) or fewer species the flat list under
the root is fine and NO intermediate rank is used. Only above that, keep the deepest
qualifying rank; coarser ranks above it are implied by it.

Rodentia (29 spp): grouping needed; suborder (4) and family (6) qualify,
  genus (18) does not -> family -> root - family - species.
Soricidae (7 spp): 7 nodes under the family is fine -> root - species, flat.

Usage: choose_hierarchy.py species.csv [cache.json]
       (CSV needs a scientificName column; other columns ignored)
       Classification comes from adapters/taxonomy/<name>.py; pick one with
       the CLAVIS_TAXONOMY environment variable (default: nortaxa).
"""
import csv, json, os, sys
from _adapters import taxonomy
tax = taxonomy()

RANKS = ["kingdom", "phylum", "subphylum", "class", "subclass", "superorder",
         "order", "suborder", "infraorder", "superfamily", "family",
         "subfamily", "tribe", "genus"]

csv_path = sys.argv[1]
cache_path = sys.argv[2] if len(sys.argv) > 2 else csv_path + ".taxonomy-cache.json"
cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}

species = [r["scientificName"].strip()
           for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"))
           if r.get("scientificName", "").strip()]

def classify(name):
    if name in cache: return cache[name]
    cache[name] = tax.resolve(name)["higher"]   # {rank: name}
    return cache[name]

cls = {s: classify(s) for s in species}
json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

FLAT_MAX = 16   # a flat list up to this size needs no grouping
n = len(species)
if n <= FLAT_MAX:
    print(f"{n} species <= {FLAT_MAX}: flat list, no intermediate rank needed")
    print("\nhierarchy: root -> species")
    raise SystemExit(0)
qualified = []
print(f"{n} species\n")
print(f"{'rank':<14}{'groups':>7}  verdict")
for rank in RANKS:
    vals = [cls[s].get(rank) for s in species]
    if any(not v for v in vals):
        missing = [s for s, v in zip(species, vals) if not v]
        print(f"{rank:<14}{'-':>7}  dropped: incomplete ({len(missing)} species lack it,"
              f" e.g. {missing[0]})")
        continue
    groups = sorted(set(vals))
    if len(groups) < 2:
        print(f"{rank:<14}{len(groups):>7}  dropped: single group (it is the root)")
    elif len(groups) > n / 2:
        print(f"{rank:<14}{len(groups):>7}  dropped: groups nothing (> {n/2:g} = half of {n})")
    else:
        qualified.append(rank)
        print(f"{rank:<14}{len(groups):>7}  qualifies")

kept = qualified[-1:] if qualified else []
for r in qualified[:-1]:
    print(f"\n{r} qualifies but is coarser than {kept[0]} -- implied, dropped")
print("\nhierarchy: root -> " + " -> ".join(kept + ["species"]))
if kept:
    for g in sorted(set(cls[s][kept[0]] for s in species)):
        members = [s for s in species if cls[s][kept[0]] == g]
        print(f"  {g}: {len(members)}")
print("\nNote: collapse any node left with a single child when building the tree.")
