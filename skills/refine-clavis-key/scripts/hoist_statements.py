#!/usr/bin/env python3
"""Phase 5: hoist statements to the highest applicable taxon.

Bottom-up: for each (parent, character), if every direct child of the
parent has the same explicit asserted-state set for that character, lift
the assertion to the parent and remove the children's copies. The
children inherit the value from the parent (Clavis lookup convention).

A child without an explicit assertion on a character blocks hoisting at
that level — there's no way to know what value the child should inherit
once the parent commits.

Statements are re-emitted from the post-hoist map with their frequencies
unchanged; only positive statements are written (zero is implied on
exclusive characters). Numerical values ([min, max]) are hoisted like states.

Usage:
  ./venv/bin/python hoist_statements.py IN.json --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))

    children_of: dict[str, list[str]] = defaultdict(list)

    def visit(taxa: list[dict]) -> None:
        for t in taxa:
            for c in t.get("children") or []:
                children_of[t["id"]].append(c["id"])
            visit(t.get("children") or [])

    visit(clavis["taxa"])

    # Post-order traversal
    post_order: list[str] = []

    def post(tid: str) -> None:
        for c in children_of.get(tid, []):
            post(c)
        post_order.append(tid)

    for t in clavis["taxa"]:
        post(t["id"])

    # asserted: (taxon, character) -> {value: frequency}; values are state ids or
    # (min, max) tuples for numerical characters. Positive frequencies only.
    asserted: dict[tuple[str, str], dict] = {}
    for s in clavis["statements"]:
        if s["frequency"] > 0:
            v = tuple(s["value"]) if isinstance(s["value"], list) else s["value"]
            asserted.setdefault((s["taxon"], s["character"]), {})[v] = s["frequency"]

    char_ids = [c["id"] for c in clavis["characters"]]

    n_hoisted = 0
    for tid in post_order:
        kids = children_of.get(tid, [])
        if len(kids) < 2:
            continue
        for char_id in char_ids:
            child_maps = [asserted.get((cid, char_id)) for cid in kids]
            if any(m is None for m in child_maps):
                continue
            first = child_maps[0]
            if not all(m == first for m in child_maps[1:]):
                continue   # whole frequency vectors must agree, not just the value sets
            existing = asserted.get((tid, char_id))
            if existing is not None and existing != first:
                continue   # parent says different; no overriding
            asserted[(tid, char_id)] = dict(first)
            for cid in kids:
                asserted.pop((cid, char_id), None)
            n_hoisted += 1

    # Re-emit positive statements only (zero is implied on exclusive characters);
    # frequencies are carried through unchanged.
    new_statements: list[dict] = []
    for (tid, char_id), vals in asserted.items():
        for v, f in vals.items():
            new_statements.append({
                "id": f"statement:{uuid.uuid4().hex}",
                "taxon": tid,
                "character": char_id,
                "value": list(v) if isinstance(v, tuple) else v,
                "frequency": f,
            })

    clavis["statements"] = new_statements
    args.out.write_text(json.dumps(clavis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Hoisted {n_hoisted} (parent, character) assertions")
    print(f"Statements: written {len(new_statements)}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
