#!/usr/bin/env python3
"""Phase 5: hoist statements to the highest applicable taxon.

Bottom-up: for each (parent, character), if every direct child of the
parent has the same explicit asserted-state set for that character, lift
the assertion to the parent and remove the children's copies. The
children inherit the value from the parent (Clavis lookup convention).

A child without an explicit assertion on a character blocks hoisting at
that level — there's no way to know what value the child should inherit
once the parent commits.

Statements are re-emitted from the post-hoist asserted map so the
frequency-rule shape is rebuilt cleanly.

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

    # Build asserted map from statements (positive-frequency entries)
    asserted: dict[tuple[str, str], set[str]] = {}
    for s in clavis["statements"]:
        if s["frequency"] > 0:
            asserted.setdefault((s["taxon"], s["character"]), set()).add(s["value"])

    # All character IDs (lookup target during hoist scan)
    char_ids = [c["id"] for c in clavis["characters"]]

    n_hoisted = 0
    for tid in post_order:
        kids = children_of.get(tid, [])
        if len(kids) < 2:
            continue
        for char_id in char_ids:
            child_sets: list[frozenset[str] | None] = []
            for cid in kids:
                v = asserted.get((cid, char_id))
                child_sets.append(frozenset(v) if v is not None else None)
            if any(s is None for s in child_sets):
                continue
            first = child_sets[0]
            if not all(s == first for s in child_sets[1:]):
                continue
            existing = asserted.get((tid, char_id))
            if existing is not None and set(existing) != set(first):
                continue  # parent says different — don't override
            asserted[(tid, char_id)] = set(first)
            for cid in kids:
                if (cid, char_id) in asserted:
                    del asserted[(cid, char_id)]
            n_hoisted += 1

    # Re-emit statements
    char_states_map = {c["id"]: [s["id"] for s in c["states"]] for c in clavis["characters"]}
    new_statements: list[dict] = []
    for (tid, char_id), state_set in asserted.items():
        if not state_set:
            continue
        all_state_ids = char_states_map.get(char_id, [])
        n = len(state_set)
        freq_pos = 1.0 if n == 1 else 0.5
        for sid in all_state_ids:
            new_statements.append({
                "id": f"statement:{uuid.uuid4().hex}",
                "taxon": tid,
                "character": char_id,
                "value": sid,
                "frequency": freq_pos if sid in state_set else 0,
            })

    clavis["statements"] = new_statements
    args.out.write_text(json.dumps(clavis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Hoisted {n_hoisted} (parent, character) assertions")
    print(f"Statements: written {len(new_statements)}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
