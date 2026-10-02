#!/usr/bin/env python3
"""Phase 4: insert genus-level taxa between a parent and its species
children, where ≥2 species share a genus epithet (the leading
capitalised word of `scientificName`).

This is pure binomial parsing — no model judgment needed for the
sprinkhanen-style clean case. The script auto-applies the inference
and writes the modified Clavis. If you ever need to override (e.g.
a species moves to a sibling genus, or an unusual genus name is
flagged), edit the output file by hand or revisit the script.

Statements stay where they are (on species). Phase 5 (statement
hoisting) lifts them up to genus/family where appropriate.

Usage:
  ./venv/bin/python infer_hierarchy.py IN.json --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path


def split_genus(sci_name: str | None) -> str | None:
    """Return the leading word of a binomial, or None."""
    if not sci_name:
        return None
    parts = sci_name.split()
    if len(parts) < 2:
        return None
    if not parts[0][:1].isupper():
        return None
    return parts[0]


def group_one_level(parent: dict) -> int:
    """Group `parent`'s direct children by genus: for each genus where
    ≥2 children share, wrap them in a new genus node. Does NOT recurse —
    callers control descent. Returns inserted-genus count at this level."""
    children = parent.get("children") or []
    if not children:
        return 0

    by_genus: dict[str, list[dict]] = defaultdict(list)
    other: list[dict] = []
    for c in children:
        g = split_genus(c.get("scientificName"))
        if g:
            by_genus[g].append(c)
        else:
            other.append(c)

    inserted = 0
    new_children: list[dict] = list(other)
    for genus, sp_list in by_genus.items():
        if len(sp_list) >= 2:
            new_children.append({
                "id": f"taxon:{uuid.uuid4().hex}",
                "scientificName": genus,
                "children": sp_list,
            })
            inserted += 1
        else:
            new_children.extend(sp_list)
    parent["children"] = new_children
    return inserted


def walk(taxa: list[dict]) -> int:
    """Recurse into pre-existing children first, then group at this level.
    Newly-created genus nodes are not re-entered — their children are
    species that share the genus by construction."""
    total = 0
    for t in taxa:
        total += walk(t.get("children") or [])
    # Group at the level of each taxon (its children are grouped here).
    for t in taxa:
        total += group_one_level(t)
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    inserted = walk(clavis["taxa"])
    # Also group the top-level taxa list, treating clavis["taxa"] as the
    # children of a virtual root — handles transcoders that emit a flat
    # species list at the top level.
    virtual_root = {"children": clavis["taxa"]}
    inserted += group_one_level(virtual_root)
    clavis["taxa"] = virtual_root["children"]
    args.out.write_text(json.dumps(clavis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Inserted {inserted} genus nodes")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
