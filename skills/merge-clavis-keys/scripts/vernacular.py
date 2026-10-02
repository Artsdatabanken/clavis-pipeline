#!/usr/bin/env python3
"""Usage: vernacular.py KEY.json [cache.json] [--lang nb] [--taxonomy nortaxa]

Fetches vernacular names from the taxonomy register and writes them onto the
taxa that lack one in the given language. Species carry a taxonID in
externalReference and are looked up by id; inner nodes (families, genera)
have none and are looked up by scientific name. Exact matching only.

Register access goes through adapters/taxonomy/<name>.py.
"""
import argparse, json, os
from _adapters import taxonomy

ap = argparse.ArgumentParser()
ap.add_argument("key")
ap.add_argument("cache", nargs="?")
ap.add_argument("--lang", default="nb", help="ISO 639-1 language of the names to fetch")
ap.add_argument("--taxonomy", default=None, help="taxonomy adapter name (default: nortaxa)")
a = ap.parse_args()
tax = taxonomy(a.taxonomy)

CACHE = a.cache or a.key.replace(".json", "") + ".vernacular-cache.json"
C = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

def lookup(tid, name):
    key = f"{a.lang}|id:{tid}" if tid else f"{a.lang}|name:{name}"
    if key not in C:
        C[key] = tax.vernacular(a.lang, taxon_id=tid, scientific_name=None if tid else name)
    return C[key]

d = json.load(open(a.key, encoding="utf-8"))
rows = []
def walk(ts):
    for t in ts:
        if not (t.get("vernacularName") or {}).get(a.lang):
            r = t.get("externalReference"); tid = None
            if isinstance(r, dict): tid = r.get("externalId")
            elif isinstance(r, list) and r: tid = r[0].get("externalId")
            try:
                n = lookup(tid, t["scientificName"])
            except Exception as e:
                rows.append((t["scientificName"], None, f"error: {e}")); walk(t.get("children", [])); continue
            if n:
                t.setdefault("vernacularName", {})[a.lang] = n
            rows.append((t["scientificName"], n, f"id {tid}" if tid else "by name"))
        walk(t.get("children", []))
walk(d["taxa"])
json.dump(C, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(d, open(a.key, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ok = sum(1 for r in rows if r[1])
print(f"{ok} of {len(rows)} taxa got a '{a.lang}' name\n")
for s, n, h in rows: print("  %-28s %-26s %s" % (s, n or "—", h))
