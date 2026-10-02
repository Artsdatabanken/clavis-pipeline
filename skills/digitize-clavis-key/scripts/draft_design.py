#!/usr/bin/env python3
"""Draft design.json from a claims file, so the digitizer edits instead of writes.

Usage:
  draft_design.py claims.jsonl --taxa species.csv --lang nb --out design.draft.json --review design.review.md

What the draft contains (all from the claims, nothing invented):
  * one character per distinct normalized trait wording, titled with the most
    frequent original wording, `traits` = every wording that normalizes to it
  * type numerical when at least half of the character's claims carry
    value_num and share a unit; unit = the most common one; min/max from data
  * otherwise exclusive, with one state per distinct normalized value and
    `values` = the original wordings of that value
  * `diagnostic_hint: true` when any claim on it is diagnostic (then the
    digitizer adds an `absent` state)
  * `taxa_count`, `single_taxon: true` when only one taxon has claims on it
The review file lists, per character, the values per taxon, and the pairs of
characters whose trait wordings overlap in words (candidates to merge into one
character), and values across characters that look like the same observable.
The digitizer's job becomes: merge trait clusters that are one observable,
merge states that a user cannot tell apart, name states, set absent states,
mark non-exclusive characters, and delete what is skipped (with a reason in
skipped.jsonl). Nothing else needs typing.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

STOP: set[str] = set()   # filled from the data: tokens in more than a third of all trait wordings carry no meaning


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()]+", " ", s).strip()


def trait_key(s: str) -> str:
    """Grouping key for a trait wording: parentheticals and a short leading 'label:' dropped."""
    s = re.sub(r"\(.*?\)", " ", str(s))
    s = re.sub(r"^\s*\S{1,12}:\s*", "", s)   # a short "label:" prefix ("figur: snuteform"), whatever the word
    return norm(s)


def toks(s: str) -> set[str]:
    return {w for w in norm(s).split() if w not in STOP and len(w) > 2}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("claims", type=Path)
    ap.add_argument("--taxa", type=Path, required=True)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--review", type=Path, required=True)
    a = ap.parse_args()

    claims = [json.loads(l) for l in a.claims.read_text(encoding="utf-8").splitlines() if l.strip()]
    listed = [r["scientificName"].strip() for r in csv.DictReader(a.taxa.open(encoding="utf-8-sig")) if r.get("scientificName", "").strip()]
    listed_n = {norm(t): t for t in listed}

    all_toks = Counter()
    for c in claims:
        all_toks.update({w for w in norm(c["trait"]).split() if len(w) > 2})
    STOP.update(w for w, n in all_toks.items() if n > len(claims) / 3)
    by_trait: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        if c.get("observable") is False or c.get("same_as"):
            continue
        by_trait[trait_key(c["trait"])].append(c)

    chars, review = [], []
    for key, lst in sorted(by_trait.items(), key=lambda kv: -len(kv[1])):
        wordings = Counter(c["trait"] for c in lst)
        title = wordings.most_common(1)[0][0]
        taxa_here = {norm(c["taxon"]) for c in lst}
        numeric = [c for c in lst if c.get("value_num")]
        units = Counter(c.get("unit") for c in numeric if c.get("unit"))
        ch = {"key": re.sub(r"[^a-z0-9]+", "_", key)[:40].strip("_") or f"c{len(chars)}",
              "title": {a.lang: title}, "traits": sorted(wordings),
              "taxa_count": len(taxa_here), "single_taxon": len(taxa_here) == 1,
              "diagnostic_hint": any(c.get("diagnostic") for c in lst)}
        if numeric and len(numeric) * 2 >= len(lst) and units:
            unit = units.most_common(1)[0][0]
            los = [c["value_num"][0] for c in numeric if c["value_num"][0] is not None]
            his = [c["value_num"][1] for c in numeric if c["value_num"][1] is not None]
            ch.update({"type": "numerical", "unit": unit})
            if los: ch["min"] = min(los)
            if his: ch["max"] = max(his)
            ch["_values_in_words"] = sorted({c["value"] for c in lst if not c.get("value_num")})
        else:
            ch["type"] = "exclusive"
            vals: dict[str, Counter] = defaultdict(Counter)
            for c in lst:
                vals[norm(c["value"])][c["value"]] += 1
            ch["states"] = [{"key": re.sub(r"[^a-z0-9]+", "_", v)[:30].strip("_") or f"s{i}",
                             "title": {a.lang: w.most_common(1)[0][0]}, "values": sorted(w)}
                            for i, (v, w) in enumerate(sorted(vals.items(), key=lambda kv: -sum(kv[1].values())))]
        chars.append(ch)
        rows = defaultdict(list)
        for c in lst:
            rows[listed_n.get(norm(c["taxon"]), c["taxon"])].append(f"{c['value']} [{c.get('qualifier', '')}] p.{c['page']}")
        review.append((title, ch["type"], len(lst), rows))

    # merge candidates: trait wordings sharing words
    pairs = []
    keys = [c for c in chars]
    for x, y in itertools.combinations(keys, 2):
        tx, ty = toks(x["title"][a.lang]), toks(y["title"][a.lang])
        if tx and ty:
            j = len(tx & ty) / len(tx | ty)
            if j >= 0.5 or norm(x["title"][a.lang]) in norm(y["title"][a.lang]) or norm(y["title"][a.lang]) in norm(x["title"][a.lang]):
                pairs.append((round(j, 2), x["title"][a.lang], y["title"][a.lang]))
    pairs.sort(reverse=True)

    design = {"taxa": [{"scientificName": t} for t in listed], "characters": chars, "same_as_excludes": [],
              "_note": "DRAFT from draft_design.py. Edit: merge characters that are one observable, merge states a user cannot tell apart, set absent states on diagnostic characters, mark non-exclusive characters, delete skipped traits (reasons go to skipped.jsonl). Remove keys starting with _ and the hint fields before scoring, or leave them; score_claims.py ignores them."}
    a.out.write_text(json.dumps(design, ensure_ascii=False, indent=1), encoding="utf-8")

    L = [f"# Design review for {a.claims.name}", "",
         f"{len(chars)} draft characters from {len(claims)} claims ({sum(1 for c in chars if c['type'] == 'numerical')} numerical, {sum(1 for c in chars if c['single_taxon'])} with a single taxon, {sum(1 for c in chars if c['diagnostic_hint'])} with a diagnostic claim).", "",
         "## Candidates to merge into one character (shared words in the trait wording)", ""]
    L += [f"- {j}: **{x}** ~ **{y}**" for j, x, y in pairs[:200]] or ["- none"]
    L += ["", "## Characters, values per taxon", ""]
    for title, typ, n, rows in review:
        L.append(f"### {title} ({typ}, {n} claims, {len(rows)} taxa)")
        for t, vs in sorted(rows.items()):
            L.append(f"- {t}: " + "; ".join(vs[:6]) + (" …" if len(vs) > 6 else ""))
        L.append("")
    a.review.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(chars)} draft characters -> {a.out}; {len(pairs)} merge candidates in {a.review}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
