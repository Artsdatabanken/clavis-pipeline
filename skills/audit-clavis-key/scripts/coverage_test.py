#!/usr/bin/env python3
"""Partition Test B as a script: does some state cover every value the source
asserts for the character? Uses the claims behind each statement.

Usage:
  coverage_test.py KEY.json claims.jsonl provenance.jsonl --out coverage-test.md

For every categorical character, every claim that supports a statement of it
is listed with the state it was mapped to; a claim whose normalized value is
not a whole-word match for any state label of that character is flagged as
"mapped by judgment" (the auditor checks it is a legitimate reading, not a
stretch). For numerical characters, every claim's parsed range must lie inside
the statement's [min, max]; a claim range outside it is a defect.

Exit 1 when a numerical claim falls outside its statement's range; judgment
mappings are warnings for the auditor, not failures.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()]+", " ", s).strip()


def read_jsonl(p: Path):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def text(x):
    return " ".join(str(v) for v in x.values()) if isinstance(x, dict) else str(x or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", type=Path)
    ap.add_argument("claims", type=Path)
    ap.add_argument("provenance", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    key = json.loads(a.key.read_text(encoding="utf-8"))
    claims = {c["id"]: c for c in read_jsonl(a.claims)}
    prov = {p["statement"]: p["claims"] for p in read_jsonl(a.provenance)}
    chars = {c["id"]: c for c in key["characters"]}
    states = {s["id"]: s for c in key["characters"] for s in c.get("states", [])}
    stmts = {s["id"]: s for s in key["statements"]}

    judgment, outside, ok = [], [], 0
    per_char = defaultdict(list)
    for sid, s in stmts.items():
        c = chars.get(s["character"])
        if not c:
            continue
        for cid in prov.get(sid, []):
            cl = claims.get(cid)
            if not cl:
                continue
            if c.get("type") == "numerical":
                vn = cl.get("value_num")
                if not vn or not isinstance(s["value"], list):
                    continue
                lo, hi = s["value"]
                clo = vn[0] if vn[0] is not None else lo
                chi = vn[1] if vn[1] is not None else hi
                if clo < lo or chi > hi:
                    outside.append((text(c["title"]), cl["taxon"], cl["value"], s["value"], cl["page"]))
                else:
                    ok += 1
            else:
                st = states.get(s["value"])
                if not st:
                    continue
                label = norm(text(st["title"]))
                v = norm(cl["value"])
                if v == label or f" {label} " in f" {v} " or f" {v} " in f" {label} ":
                    ok += 1
                else:
                    judgment.append((text(c["title"]), cl["taxon"], cl["value"], text(st["title"]), cl["page"], cl["quote"][:90]))
            per_char[text(c["title"])].append(cid)

    lines = [f"# Coverage test (Test B) for {a.key.name}\n",
             f"{ok} claims map to a state or range by wording or containment; {len(judgment)} mapped by judgment; {len(outside)} numerical claims outside their statement's range.\n"]
    if outside:
        lines.append("## Numerical claims outside the statement range (defects)\n")
        for t, tx, v, rng, pg in outside:
            lines.append(f"- {t}: {tx} p.{pg} claim `{v}` vs statement {rng}")
    if judgment:
        lines.append("\n## Mapped by judgment (check each: is the state a fair reading of the claim?)\n")
        lines.append("| character | taxon | claim value | state | page | quote |\n|---|---|---|---|---|---|")
        for t, tx, v, st, pg, q in judgment:
            lines.append(f"| {t} | {tx} | {v} | {st} | {pg} | {q} |")
    a.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[1].strip())
    return 1 if outside else 0


if __name__ == "__main__":
    sys.exit(main())
