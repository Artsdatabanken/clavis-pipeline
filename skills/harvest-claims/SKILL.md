---
name: harvest-claims
description: Extracts every observable claim a source makes about each taxon into claims.jsonl, one claim per line with trait, value, qualifier, verbatim quote and page; parses numbers and units, marks diagnostic traits and look-alike statements, removes duplicates, assigns stable ids. Runs before digitize-clavis-key, one agent per source working taxon by taxon, and gives the audit and the final gate what they measure against. Also finds each taxon's pages and the figures in a source so the harvester reads small files and crops, not whole books. Use when building a key, or when the user asks "did we miss anything in the book" or "where does this statement come from".
license: MIT
compatibility: Python 3.11+. poppler (pdftotext, pdfimages, pdftoppm) for PDFs; pypdf as fallback for text. A model with vision for figure crops. Network only for taxon_names.py.
metadata:
  author: Artsdatabanken
  version: "1.1"
  pipeline: clavis-pipeline
---

# Harvest claims from a source

**Never delete or overwrite the user's files.** New files only, under `work/<source>/`.

This skill does one thing: it turns a source into a flat inventory of claims. A claim is one observable thing the source says about one taxon: "tail longer than body", "weight 20–35 g", "belly usually white". No characters, no states, no frequencies, no decisions about what matters. Those come later, from this inventory, in `digitize-clavis-key`.

Inside `build-clavis-key` this runs on every source before digitization, one harvester agent per source that works through the taxa one at a time, and its check runs inside every audit and in the final gate. Listing what one taxon's pages say, with a verbatim quote per line, is hard to argue with and easy to check against the page; designing the key is a different job for a different agent.

## Preparing a source (the orchestrator does this once per source)

1. **Text once.** `pdftotext -layout BOOK.pdf work/<source>/full.txt` (pages separated by form feeds). Without poppler: `python -c "import pypdf,sys; r=pypdf.PdfReader(sys.argv[1]); print('\f'.join(p.extract_text() or '' for p in r.pages))" BOOK.pdf > work/<source>/full.txt`. A scanned book without a text layer goes through `tools/ocr_pdf.py --layout` first (Surya), which also writes `layout.json` with figure regions. A Word file: `tools/docx_to_text.py BOOK.docx work/<source>/full.txt` (standard library only; page breaks become form feeds).
2. **Names.** `scripts/taxon_names.py species.csv --lang <source language> --out work/<source>/names.json` adds vernacular names and abbreviated binomials; books rarely repeat the Latin name.
3. **Pages per taxon.** `scripts/find_sections.py work/<source>/full.txt --taxa species.csv --names work/<source>/names.json --pdf BOOK.pdf --out work/<source>/` (with `--pdf` the per-taxon files are in reading order, so multi-column pages are not interleaved) writes `pages.json` (the proposed section, the printed-page offset, each taxon's pages), `section.txt`, and one `<Taxon>.txt` per taxon. Confirm only the two edge pages of the section by reading them; extend the section if a taxon's description spills over. Taxa reported `NOT FOUND` or `outside section` need a look: a missing synonym in `names.json`, or the source does not treat them.
4. **Figures.** `scripts/find_figures.py BOOK.pdf --pages <section> --text work/<source>/full.txt [--layout work/<source>/layout.json] --out work/<source>/figures.json --render work/<source>/figures/` lists every figure, plate and table with a page, a crop when a bounding box is known, and the caption text. Harvesters get these PNGs. Nobody renders or reads whole pages by default.

The harvester receives: the source's folder with the `<Taxon>.txt` files, `figures.json` with the crops, the taxon list in order, and the output folder. Nothing else; never a key, never another source.

## The job (the harvester, one source, taxon by taxon)

Progress checklist, copy it and tick as you go:

```
- [ ] taxon 1 … n: read <Taxon>.txt and its figure crops, write claims/<Taxon>.jsonl, run check_claims.py on it, fix rejections
- [ ] merge: check_claims.py claims/*.checked.jsonl --out claims.jsonl
- [ ] report: claims per taxon, pages read, taxa with fewer than 5 claims
```

For each taxon in turn, with only that taxon's file open:

1. Read the taxon file. Every passage about the taxon counts: its description, its couplets in the printed key, its row in a comparison table, the figure crops listed for your pages with their labels.
2. Write one claim per observable assertion. Split bundled sentences: "stem hairy, leaves toothed, flowers yellow" is three claims; "usually white, rarely grey" is two claims with their own qualifiers. Keep the qualifier the source uses (always, usually, sometimes, rarely, or a range). Keep the verbatim quote, in the source language, and the printed page from the page marker.
3. Measurements: `value` as the source writes it (`3–6 g`, `opptil 2,5 cm`, `over 24 mm`, `up to 85 g`), plus `value_num: [min, max]` with `null` on an open side, and `unit` as written. You read the words; the checker only verifies that your numbers occur in the quote. Do not convert or round.
   - Frequency: set `qualifier` from the source's wording (always, usually, sometimes, rarely; `range` for a measurement; `comparative` for a comparison). The scripts know no words of any language; this field is where "vanligvis", "meist", "usually" become one thing.
   - Alternatives: when one sentence gives several values for one trait ("brown or grey", "svart til gråbrun"), write one claim with `values: ["brown", "grey"]` and `value` as written; or two claims when each value has its own qualifier ("usually white, rarely grey").
4. Comparative claims ("larger than X", "darker than the field vole") are claims about this taxon; record the comparison in `value` as stated, qualifier `comparative`. Do not resolve it into absolute terms; that is a later decision.
   - When the source says the taxon **cannot be told from another one** ("ingen ytre forskjeller fra sørmarkmus", "meget lik markmus", "indistinguishable from"), write one claim with `same_as` set to that taxon's scientific name (look it up on the same pages or in the taxon list; never guess). The digitizer then gives this taxon the look-alike's values for every trait the source does not state for it.
   - When the source presents a trait as **what distinguishes** the taxon (a couplet in the printed key; wording like "kjennetegnes ved", "skilles fra ... ved", "the only species with"), set `diagnostic: true`. A diagnostic trait is, by the source's own logic, lacking in the other species it describes; the digitizer scores them absent.
5. Figure labels count. Read the crop with vision and record each labeled feature as a claim with `kind: "figure"`, `quote` set to the label text and `page` to the plate.
6. Claims that cannot be observed on a specimen or find (litter size, lifespan, diet) are still recorded, with `observable: false`. The key design decides what to drop, and the final audit needs to know they were seen.
7. Open a whole page image only when the text for that page is unreadable (OCR garbage). Do not read other taxa's pages, and add nothing from your own knowledge. A claim without a quote is not a claim.
8. Write `work/<source>/claims/<Taxon>.jsonl` (fields in `references/claim-schema.md`), then run `scripts/check_claims.py work/<source>/claims/<Taxon>.jsonl --out work/<source>/claims/<Taxon>.checked.jsonl` and fix what it rejects and every `note` it adds (missing qualifier, number not in the quote, missing unit). Report the number of claims and the pages you read.

When every taxon is done, merge: `scripts/check_claims.py work/<source>/claims/*.checked.jsonl --out work/<source>/claims.jsonl`. The script normalizes, validates the fields you set, drops duplicates and assigns stable ids. It contains no words of any language: what the source means is in your fields.

## Checking the claims against the source

`scripts/source_coverage.py` is run by the auditor, never by the harvester: every quote must occur verbatim in the book, and every stretch of eight or more words on the harvester's pages that no claim quotes is listed for a decision (claims added, or no observable claim, not a listed taxon, unreadable). This is what makes "the harvester wrote down everything" a measured statement instead of a hope.

## Checking a key against the claims

Two directions, both deterministic once the key's statements carry provenance (`provenance.jsonl`, `skipped.jsonl`; formats in `references/claim-schema.md`):

```
python3 scripts/claims_vs_key.py work/<source>/claims.jsonl KEY.json --provenance provenance.jsonl --skipped skipped.jsonl --out claims-audit.md
```

- **Statement → claim**: every statement lists the claims it rests on; a numerical statement's range must cover each cited claim's number. A statement with none is reported, unless it is hoisted and every leaf under it is covered.
- **Claim → statement**: every claim appears in some statement's provenance, or in `skipped.jsonl` with a reason. Anything else is a gap.

Exit 1 on any finding. This is gate 3 of `build-clavis-key` and part of audit Phase 1.

## Checking a key that has no provenance ("did we miss anything?")

Any key made before this skill existed has no provenance. The whole procedure is yours to run from the user's one sentence; do not hand steps back.

1. Prepare the source and harvest as above.
2. `scripts/claims_vs_key.py work/<source>/claims.jsonl KEY.json --out work/claims-worksheet.md` writes a worksheet: every claim with the key's characters sharing words with it and the taxon's statements on those characters. Hints, not matches.
3. Fill in every `verdict:` line: `covered: <statement or character>` (a range containing the value counts), `skipped: <reason>` (not observable, single taxon, no variation, duplicate, out of scope), or `missing` (the source says it, it would separate taxa, the key lacks it). Open the page when the quote is not enough. Never mark covered on a word match alone.
4. Write `work/claims-audit.md`: counts, every `missing` claim with taxon, page and quote, the `covered` claims where the key is clearly coarser than the source, and one paragraph on whether the key misses discriminating information.
5. Report the counts and the missing list. If nothing is missing, say so plainly.

## What this skill does not do

- Design characters or states, bin or convert measurements, score frequencies.
- Decide what is worth keeping. Every assertion is recorded; selection happens downstream and is logged there.
- Reconcile claims across sources. One claims file per source.
