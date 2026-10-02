#!/usr/bin/env python3
"""Validate harvested claim files, normalize, parse numbers and qualifiers,
drop duplicates, assign stable ids, and merge into one claims.jsonl.

Usage:
  check_claims.py work/claims/*.jsonl --out work/claims.jsonl [--lang nb]

What it does to every claim, deterministically:
  - rejects lines with missing required fields or invalid enum values
  - normalizes whitespace and case in trait and value for duplicate detection
    (the stored text keeps the harvester's wording)
  - parses `value` into `value_num: [min, max]` and `unit` where it is a
    number, a range, or an open bound: "3-6 g" -> [3, 6]; "over 40 mm" ->
    [40, null]; "opptil 2,5 cm" -> [null, 2.5]. "2/3 av kroppslengden" is
    not parsed (a ratio in words, not a measurement).
  - sets `qualifier` from the quote when the harvester left it unspecified,
    using the per-language word list in references/qualifiers.json
  - drops claims whose normalized (source, taxon, trait, value, page) repeats
Exits 1 if anything was rejected. Prints counts per taxon.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REQUIRED = ["source", "taxon", "trait", "value", "quote", "page"]
QUALIFIERS = {"always", "usually", "sometimes", "rarely", "range", "comparative", "unspecified"}
KINDS = {"description", "key", "table", "figure"}
HERE = Path(__file__).resolve().parent
NUM = r"\d+(?:[.,]\d+)?"
UNITS = r"(mm|cm|dm|m|km|µm|um|mg|g|kg|%|s|sek|min|t|h|timer|døgn|dager|uker|måneder|år|ringer|par|stk)"
RE_RANGE = re.compile(rf"^(?:ca\.?\s*)?({NUM})\s*(?:[–‒—-]|til|to|bis|tot)\s*({NUM})\s*{UNITS}?\b", re.I)
RE_UPTO = re.compile(rf"^(?:opptil|opp til|up to|under|inntil|<|≤|høyst|max\.?|maks\.?|bis|hoogstens)\s*({NUM})\s*{UNITS}?\b", re.I)
RE_OVER = re.compile(rf"^(?:over|more than|mer enn|minst|>|≥|at least|ab|meer dan|minstens)\s*({NUM})\s*{UNITS}?\b", re.I)
RE_SINGLE = re.compile(rf"^(?:ca\.?\s*|c\.\s*|about\s*)?({NUM})\s*{UNITS}\b", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()]+", " ", s)


def num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_value(v: str):
    """Return (value_num, unit) or (None, None)."""
    s = v.strip()
    m = RE_RANGE.match(s)
    if m:
        return [num(m.group(1)), num(m.group(2))], (m.group(3) or "").lower() or None
    m = RE_UPTO.match(s)
    if m:
        return [None, num(m.group(1))], (m.group(2) or "").lower() or None
    m = RE_OVER.match(s)
    if m:
        return [num(m.group(1)), None], (m.group(2) or "").lower() or None
    m = RE_SINGLE.match(s)
    if m:
        x = num(m.group(1))
        return [x, x], m.group(2).lower()
    return None, None


def load_qualifiers(lang: str) -> dict:
    p = HERE.parent / "references" / "qualifiers.json"
    if not p.exists():
        return {}
    table = json.loads(p.read_text(encoding="utf-8"))
    return table.get(lang) or table.get("en") or {}


def guess_qualifier(text: str, words: dict) -> str | None:
    """One qualifier class found -> that class; several -> None (the claim bundles
    a usual and a rare value and must be split by the harvester)."""
    t = f" {norm(text)} "
    found = {q for q in ("rarely", "sometimes", "usually", "always")
             if any(f" {norm(w)} " in t for w in words.get(q, []))}
    found.discard("sometimes") if found - {"sometimes"} and "or" in {norm(w) for w in words.get("sometimes", [])} and found != {"sometimes"} else None
    if len(found) == 1:
        return found.pop()
    if len(found) > 1:
        return "mixed"
    return None


def claim_id(c: dict) -> str:
    key = "\x1f".join([c["source"], norm(c["taxon"]), norm(c["trait"]), norm(c["value"]), str(c["page"]).strip()])
    return "claim:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--lang", default="en", help="source language, for the qualifier word list")
    a = ap.parse_args()
    words = load_qualifiers(a.lang)

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
            vn, unit = parse_value(c["value"])
            if vn is not None:
                c["value_num"] = vn
                if unit:
                    c["unit"] = unit
                if c["qualifier"] == "unspecified":
                    c["qualifier"] = "range"
            if c["qualifier"] == "unspecified":
                g = guess_qualifier(c["value"], words) or guess_qualifier(c["quote"], words)
                if g == "mixed":
                    c["note"] = "quote carries more than one frequency word; split into one claim per value"
                elif g:
                    c["qualifier"] = g
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
    numeric = sum(1 for c in ordered if "value_num" in c)
    print(f"\n{len(ordered)} claims written to {a.out} ({dupes} duplicates dropped, {len(errors)} rejected, {numeric} with parsed numbers)")
    print("by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(per_kind.items())))
    for t, n in sorted(per_taxon.items()):
        print(f"  {t:<40} {n:>4}")
    low = [t for t, n in per_taxon.items() if n < 5]
    if low:
        print(f"\nfewer than 5 claims: {', '.join(sorted(low))} - re-check their pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
