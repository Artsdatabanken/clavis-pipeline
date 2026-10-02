#!/usr/bin/env python3
"""Validate harvested claim files, normalize, drop duplicates, assign stable
ids, and merge into one claims.jsonl.

Usage:
  check_claims.py work/claims/*.jsonl --out work/claims.jsonl

Language-neutral by design: the harvester (a model that reads the source's
language) writes the meaning into fields; this script only checks and
normalizes fields. It knows no words of any language.

What it does to every claim:
  - rejects lines with missing required fields or invalid enum values
  - normalizes whitespace, case and punctuation in trait and value for
    duplicate detection (the stored text keeps the harvester's wording)
  - checks `value_num` when the harvester gave one: two entries, numbers or
    null, min <= max, and each number appears in `value` or `quote` (digits
    only, so no language involved); parses `value_num` itself only for the
    symbol forms every language shares: "3–6 g", "3-6", "< 30 mm", "> 24",
    "≤ 2,5 cm", "40 mm"
  - `qualifier` missing -> "unspecified" with a note asking the harvester to set
    it; `diagnostic` defaults to true for claims of kind "key" (a couplet in a
    printed key is diagnostic by construction), else false
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
NUM = r"\d+(?:[.,]\d+)?"
UNIT = r"([^\W\d_]{1,8}|%)"   # a short alphabetic token after the number is its unit; no list of units
RE_RANGE = re.compile(rf"^\s*({NUM})\s*[–‒—-]\s*({NUM})\s*{UNIT}?\s*$")
RE_LE = re.compile(rf"^\s*[<≤]\s*({NUM})\s*{UNIT}?\s*$")
RE_GE = re.compile(rf"^\s*[>≥]\s*({NUM})\s*{UNIT}?\s*$")
RE_SINGLE = re.compile(rf"^\s*({NUM})\s*{UNIT}?\s*$")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()]+", " ", s)


def num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_symbol_value(v: str):
    """Only forms with digits and symbols: no words of any language."""
    m = RE_RANGE.match(v)
    if m:
        return [num(m.group(1)), num(m.group(2))], (m.group(3) or None)
    m = RE_LE.match(v)
    if m:
        return [None, num(m.group(1))], (m.group(2) or None)
    m = RE_GE.match(v)
    if m:
        return [num(m.group(1)), None], (m.group(2) or None)
    m = RE_SINGLE.match(v)
    if m and m.group(2):
        x = num(m.group(1))
        return [x, x], m.group(2)
    return None, None


def canon(x) -> str:
    """One spelling for a number however it is written: 90, 90.0, 90,0 -> '90'; 2,5 -> '2.5'."""
    return "%g" % float(str(x).replace(",", "."))


def digits_in(text: str) -> set[str]:
    return {canon(x) for x in re.findall(NUM, text)}


def claim_id(c: dict) -> str:
    key = "\x1f".join([c["source"], norm(c["taxon"]), norm(c["trait"]), norm(c["value"]), str(c["page"]).strip()])
    return "claim:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--lang", default=None, help="accepted and ignored; kept for older briefs")
    a = ap.parse_args()

    errors: list[str] = []
    claims: dict[str, dict] = {}
    dupes = notes = 0
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
            c.setdefault("kind", "description")
            c.setdefault("observable", True)
            c.setdefault("diagnostic", c["kind"] == "key")
            if c["kind"] not in KINDS:
                errors.append(f"{f}:{n}: kind {c['kind']!r} not in {sorted(KINDS)}")
                continue
            if not isinstance(c["observable"], bool) or not isinstance(c["diagnostic"], bool):
                errors.append(f"{f}:{n}: observable and diagnostic must be true or false")
                continue
            if c.get("qualifier") not in QUALIFIERS:
                if c.get("qualifier"):
                    errors.append(f"{f}:{n}: qualifier {c['qualifier']!r} not in {sorted(QUALIFIERS)}")
                    continue
                c["qualifier"] = "unspecified"
                c["note"] = "qualifier not set; set always/usually/sometimes/rarely/range/comparative from the quote"
                notes += 1
            if isinstance(c.get("values"), list) and len(c["values"]) > 1:
                pass  # explicit alternatives; the scorer matches each
            elif "values" in c:
                errors.append(f"{f}:{n}: values must be a list of two or more alternatives, else omit it")
                continue
            vn = c.get("value_num")
            if vn is None:
                vn, unit = parse_symbol_value(c["value"])
                if vn is not None:
                    c["value_num"] = vn
                    if unit and not c.get("unit"):
                        c["unit"] = unit
            if c.get("value_num") is not None:
                vn = c["value_num"]
                ok = isinstance(vn, list) and len(vn) == 2 and all(x is None or isinstance(x, (int, float)) for x in vn)
                if ok and vn[0] is not None and vn[1] is not None and vn[0] > vn[1]:
                    ok = False
                if not ok:
                    errors.append(f"{f}:{n}: value_num must be [min, max] with numbers or null, min <= max")
                    continue
                seen = digits_in(c["value"]) | digits_in(c["quote"])
                for x in vn:
                    if x is not None and canon(x) not in seen:
                        c["note"] = (c.get("note", "") + f" value_num {x} does not occur in value or quote; check it").strip()
                        notes += 1
                if c["qualifier"] == "unspecified":
                    c["qualifier"] = "range"
                if not c.get("unit"):
                    c["note"] = (c.get("note", "") + " unit missing for a number").strip()
                    notes += 1
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
    numeric = sum(1 for c in ordered if c.get("value_num"))
    print(f"\n{len(ordered)} claims written to {a.out} ({dupes} duplicates dropped, {len(errors)} rejected, {numeric} with numbers, {notes} notes for the harvester)")
    print("by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(per_kind.items())))
    for t, n in sorted(per_taxon.items()):
        print(f"  {t:<40} {n:>4}")
    low = [t for t, n in per_taxon.items() if n < 5]
    if low:
        print(f"\nfewer than 5 claims: {', '.join(sorted(low))} - re-check their pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
