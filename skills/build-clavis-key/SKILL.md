---
name: build-clavis-key
description: Orchestrates end to end, from a target taxon plus a folder of sources (PDFs, scans, existing Clavis files) to a finished, merged, measured Clavis identification key. Builds the species list through a species-list adapter (Norway: NorTaxa + alien-species list), prepares each source once (text, pages per taxon, figures), harvests claims with one agent per source, digitizes with one agent per source, audits every draft with a fresh agent, merges, runs the determinability pass, and loops on the gates until every one passes with numbers, then reports tokens and cost. Use when the user names a taxon and provides sources and wants the whole pipeline run ("make me a key for Soricidae from these books").
license: MIT
compatibility: Python 3.11+ and network access to a taxonomy register (adapters/). Best with a harness that can run sub-agents; poppler for PDFs.
metadata:
  author: Artsdatabanken
  version: "2.0"
  pipeline: clavis-pipeline
---

# Build a Clavis key for a taxon, end to end

**Never delete or overwrite the user's files.** New files only. Work in `work/` next to the sources, deliver in `leveranse/` (or `deliverables/`) next to it.

Orchestrates: species list → prepare each source → harvest claims → one key per source → audit → merge → determinability → gates. The run is not done when the key exists; it is done when every gate passes with numbers. A failing gate is work, not a result.

Progress checklist, copy it and tick as you go:

```
- [ ] run-start.txt
- [ ] 0 species list
- [ ] 0b prepare each source (text, names, sections, figures)
- [ ] 0c one harvester per source -> claims.jsonl
- [ ] 1 one digitizer per source -> draft key + provenance + skipped
- [ ] 2 one auditor per key -> *.audited.json at 0/0
- [ ] 3 merge in work/merge
- [ ] 3b determinability agent
- [ ] 4 run_gates.py until all required gates pass; deliver
```

## First thing: note the start time

Write the local date and time into `work/run-start.txt`. The token report at the end needs it.

## Ask at the start (one round, then run)

1. Checkpoint mode: straight through / pause once after the per-source keys / pause after every phase. Default: straight through when the user said so.
2. Anything unclear about the sources (page ranges, which document is which).

Everything else the pipeline decides and reports.

## Rules for every agent you spawn

- `model` set to the run's model on every spawn; never unset, never above the run's model.
- **One scratch directory per agent**, named in the brief (`work/<source>/scratch/<agent>/`). Agents sharing a scratchpad overwrote each other's files in two runs.
- **Brief = invariant part first, specifics last.** Start every brief with the same fixed lines (the repository path, "read AGENTS.md", the skill to invoke), then the per-agent paths and names at the end, no timestamps or run ids in between. A byte-identical prefix is cached across agents; the rules themselves live in the skills, never in the brief.
- Give each agent only its own small files: the taxon text file and figure crops (harvester), the claims file (digitizer), the key and claims (auditor). Never the whole book or the whole section when a smaller file exists.
- **Never stop a working agent without first having it write its state to disk.**

## Phase 0: species list

A region-specific adapter in `adapters/species-list/`. Norway: `adapters/species-list/norway.py <Taxon> [out.csv]` → `scientificName,inNorway,doorknockerRisk` from NorTaxa plus the 2023 alien-species doorknockers; exact accepted-name matches only, never similarity. Another region needs a script with the same `scientificName` column.

**Show the CSV to the user before continuing** when running with checkpoints; the doorknocker scope is theirs. Without checkpoints, report it and go on.

## Phase 0b: prepare each source once

Per source, in the orchestrator, never in an agent:

1. `pdftotext -layout BOOK.pdf work/<source>/full.txt` (scans: `tools/ocr_pdf.py --layout` first).
2. `harvest-claims/scripts/taxon_names.py species.csv --lang <source language> --out work/<source>/names.json`.
3. `harvest-claims/scripts/find_sections.py work/<source>/full.txt --taxa species.csv --names work/<source>/names.json --out work/<source>/`: section range, printed-page offset, one `<Taxon>.txt` per taxon. Confirm the two edge pages of the section by reading them; fix `names.json` for taxa not found; extend where a description spills over.
4. `harvest-claims/scripts/find_figures.py BOOK.pdf --pages <section> --text work/<source>/full.txt [--layout work/<source>/layout.json] --out work/<source>/figures.json --render work/<source>/figures/`.

An existing Clavis file among the sources (an artfakta download, a matrix export) skips harvesting and digitizing: it goes through `refine-clavis-key` (couplets decomposed per taxon along its own path, bins to numerical characters) and then `audit-clavis-key` without claims (structural phases only), and enters the merge like any other audited key.

## Phase 0c: harvest claims (one agent per source)

Spawn one `clavis-harvester` agent per source (Agent tool, subagent_type `clavis-harvester`), sources in parallel. Brief: the source folder (`work/<source>/`, with the per-taxon text files and `figures.json`), the taxon list in order, the language, the output folder, its scratch directory. The agent works through the taxa one at a time, each with only that taxon's file open, and merges its own claims file at the end. One agent per source instead of one per taxon costs a fraction of the fixed per-agent context and keeps a book's conventions (abbreviations, page layout) learned once. Harvesters never see a key or another source.

## Phase 1: one key per source (one agent per source)

Spawn one `clavis-digitizer` per source. Brief: the claims file, the species CSV, the language, the output path, title, geography (the source's own coverage), licence (the project's, as a full URL, decided once for all sources). The digitizer works from the claims (`digitize-clavis-key`): design, `score_claims.py`, generator, provenance and skipped lists, verifier and claims audit at zero before hand-off. Flat taxon list; no hierarchy.

## Phase 2: audit every draft (one fresh agent per key)

Spawn one `clavis-auditor` per key with the key, claims, provenance, skipped list, design and decisions document. Its loop ends only at verifier PASS, `check_bins.py` clean, and 0 unsupported statements, 0 unaccounted claims; the corrected key is `<source>.<taxon>.audited.json` with `provenance.audited.jsonl` and `skipped.audited.jsonl`. No key enters the merge unaudited.

For a handful of species, the audit may run in-session instead of as an agent; the fresh context is what matters.

## Phase 3: merge

`merge-clavis-keys` on all audited keys plus the CSV, in `work/merge/`: union, `spec.json` from `concordance_candidates.py` and your reading, `reconcile.py`, `cleanup_location.py`, hierarchy from the adapter, then Phase 3b, then `coarsen.py`, `finalize.py`, metadata, vernacular names.

## Phase 3b: determinability (one fresh agent)

Spawn `clavis-usability` on the hierarchy-built key. It returns the key with shades merged (through the measured coarsening), comparatives rewritten or removed, bundles split, leftover bins converted, each change as a rename file and each removal in `removed.json`. Continue the merge from its output.

## Phase 4: the gate loop, then deliver

```
python3 skills/build-clavis-key/scripts/run_gates.py KEY.json --csv species.csv --sources work --out leveranse \
    --spec work/merge/spec.json --alias work/merge/alias.json --removed work/merge/removed.json \
    --rename work/merge/coarsen/step-01.json ... --source-keys work/merge/src/*.json \
    --run-start work/run-start.txt --match <sources folder name>
```

Gates: 1 verifier, 2 bins and numerical ranges, 3 claims audit per source (0 / 0), 4 round-trip (0 LOST), 5 redundancy (reported; pairs no source separates are source limits), 6 geography (no pair separated only by location), 7 coverage (reported), 8 tokens and cost. When a required gate fails, fix the cause where it lives (the digitizer's design, `spec.json`, a rename chain), re-run every gate, repeat. Stop only when all pass, or when the only findings are claims on a skipped list with a reason or pairs no source separates, both reported as source limits with the evidence.

`gates.md` goes at the top of the final report. Then the key file and the companions: `decisions.md` (the merge's judgment calls, in the key's language), `roundtrip-report.md`, `redundancy-report.md`, `removed-characters.md`, `coverage.md`, `tokens.md`. Markdown; PDF only when `md_to_pdf.py`'s dependencies are installed, and then only at the very end.

## Reporting

Plain language, no internal step numbers. What was built, what was decided and why, what the key cannot do (pairs no source separates, species no source covers) as source limits with which kind of source would fix them, and what the run cost (tokens by kind, price, wall-clock). Decisions are reported with their reasoning when made, not asked. When the user asks "where is it", the deliverable should already be on disk and named in the report.
