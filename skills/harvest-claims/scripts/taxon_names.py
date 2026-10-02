#!/usr/bin/env python3
"""Extra names per taxon for find_sections.py: vernacular names from the
taxonomy adapter in one or more languages, plus abbreviated binomials.

Usage:
  taxon_names.py species.csv --lang nb [--lang sv] --out names.json [--taxonomy nortaxa]

Output: {"Sorex minutus": ["dvergspissmus", "S. minutus"], ...}
Network: one adapter call per taxon per language, cached in names.json.cache.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from _adapters import taxonomy


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--lang", action="append", default=[])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--taxonomy", default=None)
    a = ap.parse_args()
    tax = taxonomy(a.taxonomy)
    cache_p = a.out.with_suffix(a.out.suffix + ".cache")
    cache = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    taxa = [r["scientificName"].strip() for r in csv.DictReader(a.csv.open(encoding="utf-8-sig")) if r.get("scientificName", "").strip()]
    out = {}
    for t in taxa:
        names = []
        g, *rest = t.split()
        if rest:
            names.append(f"{g[0]}. {' '.join(rest)}")
        for lang in a.lang:
            key = f"{lang}|{t}"
            if key not in cache:
                try:
                    cache[key] = tax.vernacular(lang, scientific_name=t)
                except Exception as e:  # network or lookup failure: record, continue
                    cache[key] = None
                    print(f"  {t} [{lang}]: {e}", file=sys.stderr)
            if cache[key]:
                names.append(cache[key])
        out[t] = names
    cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(out)} taxa, {sum(len(v) for v in out.values())} extra names -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
