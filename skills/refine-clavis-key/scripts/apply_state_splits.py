#!/usr/bin/env python3
"""Phase 3 APPLY step: split bundled states into atomic states.

Decisions format:
{
  "splits": [
    {
      "state_id": "state:abc...",
      "atomic_labels": ["label A", "label B", ...]
    },
    ...
  ]
}

Per split: the bundled state is removed from its character; for each
atomic_label, find an existing state in the character with that label
or create a new one. Every taxon that asserted (freq>0) the bundled
state now asserts the atomic states with paired uncertain frequencies
(0.5 each) — never excluding any value the source admitted.

Usage:
  ./venv/bin/python apply_state_splits.py IN.json decisions.json --out OUT.json
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path


def primary_lang(clavis: dict) -> str:
    return (clavis.get("language") or ["en"])[0]


def loc(obj: dict | None, lang: str) -> str:
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("decisions", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    lang = primary_lang(clavis)

    # Index: state_id → character_id
    state_to_char: dict[str, str] = {}
    for c in clavis["characters"]:
        for s in c.get("states") or []:
            state_to_char[s["id"]] = c["id"]

    # Deep-ish copy chars so we can mutate
    chars = [dict(c) for c in clavis["characters"]]
    for c in chars:
        c["states"] = [dict(s) for s in c.get("states") or []]
    char_by_id = {c["id"]: c for c in chars}

    # state_remap: bundled state_id → list of atomic state ids it splits into
    state_remap: dict[str, list[str]] = {}
    states_to_drop: dict[str, set[str]] = defaultdict(set)
    n_new_states = 0
    n_reused_states = 0

    for split in decisions.get("splits", []):
        bundled_id = split["state_id"]
        atomic_labels: list[str] = split["atomic_labels"]
        cid = state_to_char.get(bundled_id)
        if cid is None:
            raise SystemExit(f"State {bundled_id} not found in any character")
        char = char_by_id[cid]
        # Build label → existing state id index
        label_idx: dict[str, str] = {}
        for s in char["states"]:
            if s["id"] == bundled_id:
                continue  # exclude the state being split itself
            label_idx.setdefault(loc(s.get("title"), lang), s["id"])

        atomic_ids: list[str] = []
        for lab in atomic_labels:
            if lab in label_idx:
                atomic_ids.append(label_idx[lab])
                n_reused_states += 1
            else:
                new_sid = f"state:{uuid.uuid4().hex}"
                char["states"].append({"id": new_sid, "title": {lang: lab}})
                label_idx[lab] = new_sid
                atomic_ids.append(new_sid)
                n_new_states += 1
        state_remap[bundled_id] = atomic_ids
        states_to_drop[cid].add(bundled_id)

    # Drop the bundled states from their characters
    for cid, drop_ids in states_to_drop.items():
        char = char_by_id[cid]
        char["states"] = [s for s in char["states"] if s["id"] not in drop_ids]

    # Re-emit statements: union the assertions across split state IDs
    by_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in clavis["statements"]:
        ch = s["character"]
        new_sids = state_remap.get(s["value"], [s["value"]])
        if s["frequency"] > 0:
            by_group[(s["taxon"], ch)].update(new_sids)
        else:
            by_group.setdefault((s["taxon"], ch), set())

    new_statements: list[dict] = []
    dropped = 0
    for (tx, ch), asserted in by_group.items():
        char = char_by_id.get(ch)
        if char is None:
            continue
        all_state_ids = [s["id"] for s in char["states"]]
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
    refined["characters"] = chars
    refined["statements"] = new_statements

    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False), encoding="utf-8")
    n_splits = len(decisions.get("splits", []))
    print(f"Applied {n_splits} splits: {n_new_states} new atomic states created, "
          f"{n_reused_states} reused existing siblings")
    print(f"Statements: {len(clavis['statements'])} → {len(refined['statements'])}")
    if dropped:
        print(f"Dropped {dropped} empty (taxon, character) groups after re-emission")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
