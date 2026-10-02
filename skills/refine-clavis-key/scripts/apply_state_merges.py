#!/usr/bin/env python3
"""Phase 2 APPLY step: consume a state-merge decisions JSON and write a
refined Clavis with the chosen states merged within each character.

Decisions format:
{
  "merges": [
    {
      "character_id": "character:abcd...",
      "kept_state_id":  "state:wxyz...",
      "removed_state_ids": ["state:1111...", "state:2222..."]
    },
    ...
  ]
}

Per merge: drop the `removed_state_ids` from the character's state list.
Re-emit every (taxon, character) statement group: any taxon that asserted
a removed state now asserts the kept state instead, and we recompute
frequencies (one 1 if exactly one state remains asserted; 0.5 each if
multiple). This guarantees the frequency-rule shape stays valid.

Usage:
  ./venv/bin/python apply_state_merges.py IN.json decisions.json --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("decisions", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    clavis = load(args.infile)
    decisions = load(args.decisions)

    # Build state remap: removed_state_id → kept_state_id
    state_remap: dict[str, str] = {}
    chars_to_drop_states: dict[str, set[str]] = defaultdict(set)
    for m in decisions.get("merges", []):
        cid = m["character_id"]
        kept = m["kept_state_id"]
        for removed in m["removed_state_ids"]:
            if removed in state_remap:
                raise SystemExit(f"State {removed} appears in two merges")
            if removed == kept:
                raise SystemExit(f"State {kept} listed as both kept and removed")
            state_remap[removed] = kept
            chars_to_drop_states[cid].add(removed)

    # Drop merged-out states from their characters
    chars_out: list[dict] = []
    for c in clavis["characters"]:
        new_c = dict(c)
        drop = chars_to_drop_states.get(c["id"], set())
        new_c["states"] = [dict(s) for s in (c.get("states") or []) if s["id"] not in drop]
        chars_out.append(new_c)

    char_by_id = {c["id"]: c for c in chars_out}

    # Re-point statements; collect by group; re-emit with valid frequency shape.
    by_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in clavis["statements"]:
        sid = state_remap.get(s["value"], s["value"])
        if s["frequency"] > 0:
            by_group[(s["taxon"], s["character"])].add(sid)
        else:
            by_group.setdefault((s["taxon"], s["character"]), set())

    new_statements: list[dict] = []
    dropped = 0
    for (tx, ch), asserted in by_group.items():
        char = char_by_id.get(ch)
        if char is None:
            continue
        all_state_ids = [s["id"] for s in char["states"]]
        # Drop any asserted state IDs that no longer exist (defensive)
        asserted = {sid for sid in asserted if sid in set(all_state_ids)}
        if not asserted:
            dropped += 1
            continue
        n = len(asserted)
        freq_pos = 1.0 if n == 1 else 0.5
        for sid in all_state_ids:
            new_statements.append({
                "id": f"statement:{uuid.uuid4().hex}",
                "taxon": tx,
                "character": ch,
                "value": sid,
                "frequency": freq_pos if sid in asserted else 0,
            })

    refined = dict(clavis)
    refined["characters"] = chars_out
    refined["statements"] = new_statements

    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False), encoding="utf-8")
    n_merges = len(decisions.get("merges", []))
    n_states_removed = sum(len(m["removed_state_ids"]) for m in decisions.get("merges", []))
    print(f"Applied {n_merges} merges, removed {n_states_removed} states")
    print(f"Statements: {len(clavis['statements'])} → {len(refined['statements'])}")
    if dropped:
        print(f"Dropped {dropped} empty (taxon, character) groups after re-emission")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
