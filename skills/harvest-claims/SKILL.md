---
name: harvest-claims
description: Extract every observable claim a source makes about each taxon into a claims.jsonl file, one claim per line with trait, value, qualifier, verbatim quote and page. One job per taxon (or page chunk), no character design, no scoring. Use before digitize-clavis-key to give it a complete, checkable inventory of what the source asserts, and after a key is finished to check both directions: every statement traces to a claim, every claim reached the key or was deliberately skipped. Also use when the user asks "did we miss anything in the book" or "where does this statement come from".
license: MIT
compatibility: Python 3.11+. A model with vision for figure plates; text-only otherwise. No network.
metadata:
  author: Artsdatabanken
  version: "0.1"
  pipeline: clavis-pipeline
---

# Harvest claims from a source

**Never delete or overwrite the user's files.** New files only.

This skill does one thing: it turns a source into a flat inventory of claims. A claim is one observable thing the source says about one taxon: "tail longer than body", "weight 20–35 g", "belly usually white, occasionally gray". No characters, no states, no frequencies, no decisions about what matters. Those come later, from this inventory, in `digitize-clavis-key`.

Inside `build-clavis-key` this runs on every source before digitization (Phase 0c), and its check runs inside every audit and in the final gate. Why a separate job: a digitizer reading forty pages and designing a key at the same time skips things. A harvester that only has to list what one species' pages say, in a fresh context, with a verbatim quote for each line, is hard to argue with and easy to check against the page.

## Inputs to gather (ask only if missing)

- **Source**: the extracted text (see `digitize-clavis-key/references/source-extraction.md`) and the page images, or a PDF with a text layer.
- **Taxon list**: the species CSV from `build-clavis-key`, or the list of taxa the source covers. One job per taxon.
- **Output folder**: `work/claims/` next to the source. One file per taxon, merged at the end.

## The job, per taxon

1. Find every passage about the taxon: its description, its couplets in the printed key, its row in any comparison table, its figure plates and their labels. Note the pages.
2. Write one claim per observable assertion. Split bundled sentences: "stem hairy, leaves toothed, flowers yellow" is three claims. Keep the qualifier the source uses: always, usually, sometimes, rarely, or a range with units. Keep the verbatim quote, in the source language, and the page.
3. Comparative claims ("larger than X", "unlike Y, lacks Z") are claims about this taxon; record the comparison in `value` as the source states it. Do not resolve it into absolute terms.
4. Figure labels count. Read the plate with vision, and record each labeled feature as a claim with `quote` set to the label text and `page` to the plate.
5. Claims that cannot be observed on a specimen or find (litter size, lifespan, diet) are still recorded; mark them `observable: false`. The key design step decides what to drop, and the final audit needs to know they were seen.
6. Do not look at other taxa's pages to fill gaps, and do not add what you know from elsewhere. A claim without a quote is not a claim.

Write the claims as JSON lines; the fields are in `references/claim-schema.md`. Then:

```
python3 scripts/check_claims.py work/claims/*.jsonl --out work/claims.jsonl
```

This validates every line, drops exact duplicates, assigns stable ids, and prints counts per taxon. Fix what it rejects and re-run.

## Checking a key against the claims

Two directions, both deterministic once the key's statements carry provenance.

```
python3 scripts/claims_vs_key.py work/claims.jsonl KEY.json --provenance work/provenance.jsonl --skipped work/skipped.jsonl --out work/claims-audit.md
```

- **Statement → claim**: every statement in the key lists the claim ids it came from (`provenance.jsonl`). A statement with none is reported, unless it is inherited from an ancestor the script can prove.
- **Claim → statement**: every claim appears in some statement's provenance, or in `skipped.jsonl` with a reason. Anything else is a gap.

Formats for `provenance.jsonl` and `skipped.jsonl` are in `references/claim-schema.md`.

## Checking a key that has no provenance ("did we miss anything?")

Any key made before this skill existed has no provenance. The whole procedure, from the user naming a source and a finished key to a written answer, is yours to run; do not hand steps back to the user.

1. Harvest the claims as above, one job per taxon, into `work/claims/`, then merge with `check_claims.py`. Fix rejections yourself.
2. Build the worksheet:

   ```
   python3 scripts/claims_vs_key.py work/claims.jsonl KEY.json --out work/claims-worksheet.md
   ```

   It lists every claim with the key's characters that share words with it, and the taxon's statements on those characters. The candidates are hints, not matches.
3. Fill in every `verdict:` line in the worksheet. Exactly one of:
   - `covered: <statement id or character title>`: the key encodes this claim for this taxon, possibly in coarser terms (a bin that contains the value counts).
   - `skipped: <reason>`: not observable, single-taxon trait, no variation across taxa, duplicate, out of scope.
   - `missing`: the source says it, it would separate taxa, and the key does not have it.
   Decide from the quote and the key, and open the source page when the quote is not enough. Do not mark `covered` on a word match alone.
4. Write `work/claims-audit.md`: the counts (covered, skipped by reason, missing), every `missing` claim with taxon, page and quote, and a short list of the `covered` claims where the key is clearly coarser than the source. End with one paragraph: does the key miss discriminating information, and where.
5. Report the counts and the missing list to the user. If nothing is missing, say so plainly.

This procedure is also the test of whether harvesting is worth doing before digitization: the number of `missing` claims is the answer.

## What this skill does not do

- Design characters or states, bin measurements, or score frequencies.
- Decide what is worth keeping. Every assertion is recorded; selection happens downstream and is logged there.
- Reconcile claims across sources. One claims file per source.
