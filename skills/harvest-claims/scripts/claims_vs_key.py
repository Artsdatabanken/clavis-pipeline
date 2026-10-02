#!/usr/bin/env python3
"""Final audit in both directions between a claims file and a Clavis key.

Usage:
  claims_vs_key.py CLAIMS.jsonl KEY.json --provenance PROV.jsonl [--skipped SKIP.jsonl] --out REPORT.md
  claims_vs_key.py CLAIMS.jsonl KEY.json --out WORKSHEET.md          (key without provenance)

With --provenance (exact mode):
  A. statement -> claim: every statement lists the claim ids it rests on.
     Statements with none are reported, except statements on an internal
     taxon whose every leaf descendant is covered by claims for that
     character (a hoisted statement).
  B. claim -> statement: every claim id appears in some statement's
     provenance or in the skipped file. Anything else is a gap.
  Exit 1 if either direction has findings.

Without --provenance (worksheet mode):
  Writes, per claim, the key's characters whose title or state labels share
  words with the claim's trait or value, with the taxon's statements on those
  characters. The model fills in the verdict column: covered / skipped / missing.
  Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def read_jsonl(p: Path | None) -> list[dict]:
    if not p:
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def text(x) -> str:
    if isinstance(x, dict):
        return " ".join(str(v) for v in x.values())
    return str(x or "")


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[^\W\d_]{3,}", s.lower())}


def walk_taxa(taxa, parent=None, out=None, parent_of=None):
    if out is None:
        out, parent_of = {}, {}
    for t in taxa:
        out[t["id"]] = t
        if parent:
            parent_of[t["id"]] = parent
        walk_taxa(t.get("children", []), t["id"], out, parent_of)
    return out, parent_of


def leaves_under(tid, taxa):
    kids = taxa[tid].get("children", [])
    if not kids:
        return [tid]
    return [l for k in kids for l in leaves_under(k["id"], taxa)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("claims", type=Path)
    ap.add_argument("key", type=Path)
    ap.add_argument("--provenance", type=Path)
    ap.add_argument("--skipped", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    claims = {c["id"]: c for c in read_jsonl(a.claims)}
    key = json.loads(a.key.read_text(encoding="utf-8"))
    taxa, parent_of = walk_taxa(key["taxa"])
    chars = {c["id"]: c for c in key["characters"]}
    states = {s["id"]: (c["id"], s) for c in key["characters"] for s in c.get("states", [])}
    sci = {tid: t.get("scientificName", tid) for tid, t in taxa.items()}
    by_sci = defaultdict(list)
    for tid, name in sci.items():
        by_sci[name.lower()].append(tid)
    out: list[str] = []

    if a.provenance:
        prov = {p["statement"]: p for p in read_jsonl(a.provenance)}
        skipped = {s["claim"]: s for s in read_jsonl(a.skipped)}
        stmts = {s["id"]: s for s in key["statements"]}
        claims_by_taxon_char = defaultdict(set)
        for sid, p in prov.items():
            s = stmts.get(sid)
            if s:
                for cid in p["claims"]:
                    claims_by_taxon_char[(s["taxon"], s["character"])].add(cid)

        # A. statement -> claim
        unsupported = []
        for sid, s in stmts.items():
            p = prov.get(sid)
            if p and p["claims"]:
                for cid in p["claims"]:
                    if cid not in claims:
                        unsupported.append((sid, f"references unknown claim {cid}"))
                    elif isinstance(s["value"], list) and claims[cid].get("value_num"):
                        lo, hi = s["value"]; vn = claims[cid]["value_num"]
                        clo = vn[0] if vn[0] is not None else lo
                        chi = vn[1] if vn[1] is not None else hi
                        if clo < lo or chi > hi:
                            unsupported.append((sid, f"range {s['value']} does not cover claim {cid} ({claims[cid]['value']})"))
                continue
            if s["taxon"] in taxa and taxa[s["taxon"]].get("children"):
                leaves = leaves_under(s["taxon"], taxa)
                covered = [l for l in leaves if claims_by_taxon_char.get((l, s["character"]))]
                if len(covered) == len(leaves):
                    continue  # hoisted: every leaf has claims for this character
                unsupported.append((sid, f"hoisted on {sci[s['taxon']]} but only {len(covered)}/{len(leaves)} leaves have claims for '{text(chars.get(s['character'], {}).get('title'))}'"))
                continue
            unsupported.append((sid, p.get("note", "no claims listed") if p else "no provenance line"))

        # B. claim -> statement
        used = {cid for p in prov.values() for cid in p["claims"]}
        gaps = [c for cid, c in claims.items() if cid not in used and cid not in skipped]
        bad_skips = [cid for cid in skipped if cid not in claims]

        out.append(f"# Claims audit: {a.key.name}\n")
        out.append(f"{len(stmts)} statements, {len(claims)} claims, {len(prov)} provenance lines, {len(skipped)} skipped.\n")
        out.append(f"## A. Statements without support ({len(unsupported)})\n")
        for sid, why in unsupported:
            s = stmts[sid]
            val = s["value"] if isinstance(s["value"], list) else text(states.get(s["value"], (None, {}))[1].get("title"))
            out.append(f"- `{sid}` {sci.get(s['taxon'], s['taxon'])} / {text(chars.get(s['character'], {}).get('title'))} = {val}: {why}")
        out.append(f"\n## B. Claims that reached neither a statement nor the skipped list ({len(gaps)})\n")
        for c in sorted(gaps, key=lambda c: (c["taxon"], str(c["page"]))):
            out.append(f"- `{c['id']}` {c['taxon']} p.{c['page']}: {c['trait']} = {c['value']}  ({c['quote']})")
        if bad_skips:
            out.append(f"\n## Skipped ids that are not claims ({len(bad_skips)})\n")
            out.extend(f"- {cid}" for cid in bad_skips)
        a.out.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"A: {len(unsupported)} unsupported statements; B: {len(gaps)} unaccounted claims -> {a.out}")
        return 1 if (unsupported or gaps or bad_skips) else 0

    # worksheet mode
    char_words = {cid: words(text(c.get("title"))) | {w for s in c.get("states", []) for w in words(text(s.get("title")))}
                  for cid, c in chars.items()}
    stmts_by_taxon = defaultdict(list)
    for s in key["statements"]:
        stmts_by_taxon[s["taxon"]].append(s)

    out.append(f"# Claims worksheet: {a.key.name}\n")
    out.append("For each claim, decide: covered (name the statement), skipped (reason), or missing. Candidates are characters sharing words with the claim; they are hints, not matches.\n")
    unmatched_taxa = set()
    for c in sorted(claims.values(), key=lambda c: (c["taxon"], str(c["page"]))):
        tids = by_sci.get(c["taxon"].lower(), [])
        if not tids:
            unmatched_taxa.add(c["taxon"])
        cw = words(c["trait"]) | words(c["value"])
        cands = sorted(((len(cw & w), cid) for cid, w in char_words.items() if cw & w), reverse=True)[:4]
        out.append(f"\n### `{c['id']}` {c['taxon']} p.{c['page']}\n")
        out.append(f"{c['trait']} = {c['value']} [{c['qualifier']}]  \n> {c['quote']}\n")
        if not cands:
            out.append("candidates: none")
        for _, cid in cands:
            ch = chars[cid]
            line = f"- {text(ch.get('title'))}"
            own = [s for t in tids for s in stmts_by_taxon.get(t, []) if s["character"] == cid]
            # include inherited statements
            for t in tids:
                p = parent_of.get(t)
                while p:
                    own += [s for s in stmts_by_taxon.get(p, []) if s["character"] == cid]
                    p = parent_of.get(p)
            if own:
                vals = ", ".join(
                    (str(s["value"]) if isinstance(s["value"], list) else text(states.get(s["value"], (None, {}))[1].get("title")))
                    + f" ({s['frequency']})" for s in own)
                line += f": {vals}"
            else:
                line += ": no statement for this taxon"
            out.append(line)
        out.append("\nverdict: ")
    if unmatched_taxa:
        out.insert(2, "Taxa in the claims file with no match in the key: " + ", ".join(sorted(unmatched_taxa)) + "\n")
    a.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"worksheet with {len(claims)} claims -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
