#!/usr/bin/env python3
"""Validate harvested claim files, drop exact duplicates, assign stable ids,
and merge them into one claims.jsonl.

Usage:
  check_claims.py work/claims/*.jsonl --out work/claims.jsonl

Rejects a line when a required field is missing or empty, when `qualifier`,
`kind` or `observable` has a value outside the allowed set, or when the line
is not valid JSON. Prints every rejection with file and line number, then
counts per taxon. Exits 1 if anything was rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REQUIRED = ["source", "taxon", "trait", "value", "quote", "page"]
QUALIFIERS = {"always", "usually", "sometimes", "rarely", "range", "comparative", "unspecified"}
KINDS = {"description", "key", "table", "figure"}


def claim_id(c: dict) -> str:
    key = "\x1f".join(str(c[k]).strip() for k in ("source", "taxon", "quote", "page")) + "\x1f" + c["trait"].strip()
    return "claim:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    errors: list[str] = []
    claims: dict[str, dict] = {}
    dupes = 0
    for f in a.files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                c = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{f}:{n}: not JSON ({e})")
                continue
            missing = [k for k in REQUIRED if not str(c.get(k, "")).strip()]
            if missing:
                errors.append(f"{f}:{n}: missing {', '.join(missing)}")
                continue
            c.setdefault("qualifier", "unspecified")
            c.setdefault("kind", "description")
            c.setdefault("observable", True)
            if c["qualifier"] not in QUALIFIERS:
                errors.append(f"{f}:{n}: qualifier {c['qualifier']!r} not in {sorted(QUALIFIERS)}")
                continue
            if c["kind"] not in KINDS:
                errors.append(f"{f}:{n}: kind {c['kind']!r} not in {sorted(KINDS)}")
                continue
            if not isinstance(c["observable"], bool):
                errors.append(f"{f}:{n}: observable must be true or false")
                continue
            cid = claim_id(c)
            if cid in claims:
                dupes += 1
                continue
            c["id"] = cid
            claims[cid] = c

    for e in errors:
        print(e)
    ordered = sorted(claims.values(), key=lambda c: (c["source"], c["taxon"], str(c["page"]), c["trait"]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in ordered), encoding="utf-8")

    per_taxon = Counter(c["taxon"] for c in ordered)
    per_kind = Counter(c["kind"] for c in ordered)
    print(f"\n{len(ordered)} claims written to {a.out} ({dupes} exact duplicates dropped, {len(errors)} rejected)")
    print("by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(per_kind.items())))
    for t, n in sorted(per_taxon.items()):
        print(f"  {t:<40} {n:>4}")
    low = [t for t, n in per_taxon.items() if n < 5]
    if low:
        print(f"\nfewer than 5 claims: {', '.join(sorted(low))} - re-check their pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
