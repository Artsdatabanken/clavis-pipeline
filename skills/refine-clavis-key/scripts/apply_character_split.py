#!/usr/bin/env python3
"""Split a character whose states span multiple observable axes into N
new characters, one per axis. Each original state decomposes into one
or more (new_char, new_state) assignments — possibly only one axis if
the state describes only that.

Decisions format:
{
  "character_splits": [
    {
      "original_character_id": "character:abc...",
      "new_characters": [
        {"title": "Lichaam — Basiskleur",
         "states": ["bruin", "zwart", "geel", ...]},
        {"title": "Lichaam — Patroon",
         "states": ["eenkleurig", "bont", "gevlekt", ...]}
      ],
      "state_mapping": {
        "<original_state_id>": [
          {"new_char_index": 0, "new_state_label": "groen"},
          {"new_char_index": 1, "new_state_label": "vele kleine stippels"}
        ],
        ...
      }
    }
  ]
}

For each original assertion of state X by a taxon: emit assertions on
every (new_char, new_state) pair listed in `state_mapping[X]`. If
multiple original states map to the same new_char, the assertion sets
union (paired uncertain frequencies on the new_char).

Original character is removed; original statements are dropped.
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("decisions", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))
    lang = primary_lang(clavis)

    # Build new chars + collect per-split mapping: original_state_id → list of (new_char_id, new_state_id)
    chars_to_drop: set[str] = set()
    state_remap: dict[str, list[tuple[str, str]]] = defaultdict(list)
    new_chars: list[dict] = []

    for split in decisions.get("character_splits", []):
        orig_id = split["original_character_id"]
        chars_to_drop.add(orig_id)

        # Materialize new chars with fresh IDs
        new_char_ids: list[str] = []
        # For each new char, build label → state_id index
        char_label_to_id: list[dict[str, str]] = []
        for nc in split["new_characters"]:
            ncid = f"character:{uuid.uuid4().hex}"
            new_char_ids.append(ncid)
            label_idx: dict[str, str] = {}
            states_out: list[dict] = []
            for label in nc["states"]:
                sid = f"state:{uuid.uuid4().hex}"
                states_out.append({"id": sid, "title": {lang: label}})
                label_idx[label] = sid
            char_label_to_id.append(label_idx)
            new_chars.append({
                "id": ncid,
                "title": {lang: nc["title"]},
                "type": "exclusive",
                "states": states_out,
            })

        # Build state_remap from the mapping
        for old_sid, mappings in split["state_mapping"].items():
            for m in mappings:
                idx = m["new_char_index"]
                label = m["new_state_label"]
                if label not in char_label_to_id[idx]:
                    raise SystemExit(
                        f"Decision references unknown new_state_label {label!r} "
                        f"in new_char_index {idx} (original state {old_sid})"
                    )
                state_remap[old_sid].append((new_char_ids[idx], char_label_to_id[idx][label]))

    if not chars_to_drop:
        print("No splits in decisions. Output = input.")
        args.out.write_text(json.dumps(clavis, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    # Drop original chars; append new chars
    chars_after = [c for c in clavis["characters"] if c["id"] not in chars_to_drop] + new_chars
    char_by_id = {c["id"]: c for c in chars_after}

    # Build by-group asserted set; route via state_remap
    by_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in clavis["statements"]:
        if s["character"] in chars_to_drop:
            # Map this assertion to the new chars/states
            if s["frequency"] > 0:
                for new_cid, new_sid in state_remap.get(s["value"], []):
                    by_group[(s["taxon"], new_cid)].add(new_sid)
        else:
            # Untouched character; preserve as-is
            if s["frequency"] > 0:
                by_group[(s["taxon"], s["character"])].add(s["value"])
            else:
                by_group.setdefault((s["taxon"], s["character"]), set())

    # Re-emit
    new_statements: list[dict] = []
    for (tx, ch), asserted in by_group.items():
        char = char_by_id.get(ch)
        if char is None:
            continue
        all_state_ids = [s["id"] for s in char["states"]]
        asserted = {sid for sid in asserted if sid in set(all_state_ids)}
        if not asserted:
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

    # Characters are always exclusive; taxa asserting several states express
    # variability via paired 0.5 frequencies, never via type=non-exclusive.
    for c in chars_after:
        if "type" in c:
            c["type"] = "exclusive"

    refined = dict(clavis)
    refined["characters"] = chars_after
    refined["statements"] = new_statements

    args.out.write_text(json.dumps(refined, indent=2, ensure_ascii=False), encoding="utf-8")
    n_splits = len(decisions.get("character_splits", []))
    n_new_chars = len(new_chars)
    n_dropped = len(chars_to_drop)
    print(f"Applied {n_splits} character split(s): {n_dropped} dropped, {n_new_chars} new")
    print(f"Statements: {len(clavis['statements'])} → {len(refined['statements'])}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
