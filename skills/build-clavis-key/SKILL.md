---
name: build-clavis-key
description: End-to-end orchestration - from a target taxon plus a folder of source documents (PDFs, existing Clavis files) to a finished, merged, verified Clavis identification key. Builds the species list from a national register through a species-list adapter (Norway: NorTaxa + Fremmedartslista), spins up one independent digitize agent per source, audits every draft, then merges with merge-clavis-keys. Use when the user names a taxon and provides sources and wants the whole pipeline run ("make me a key for Soricidae from these books").
license: MIT
compatibility: Python 3.11+ and network access to a taxonomy register (adapters/). Best with a harness that can run sub-agents.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Build a Clavis key for a taxon, end to end

**Never delete or overwrite the user's files.** New files only.

Orchestrates: species list → one key per source (agents) → audit → merge → verify. The Norwegian rodent key was the worked example of the whole pipeline; its decisions document (not included in this repository) is where every judgment call this skill now encodes was made.

## First thing: note the start time

Write the local date and time of the start into `work/run-start.txt`. The final report needs it for the token count.

## Ask at the start (one round of questions, then run)

1. **Checkpoint mode** — run straight through / pause once after the per-source keys (recommended: source-reading errors are cheapest to catch there) / pause after every phase.
2. Anything unclear about the sources (page ranges, which document is which, a source still being prepared).

Everything else is decided by the pipeline and reported, not asked.

## Phase 0 — species list

The species list comes from a region-specific adapter in `adapters/species-list/`. For Norway: `adapters/species-list/norway.py <Taxon> [out.csv]` → `<taxon>_norway.csv` with `scientificName,inNorway,doorknockerRisk`:

- NorTaxa subtree export (`nortaxa.artsdatabanken.no/api/v1/DataTransfer/Export`), accepted species with `ExistsInNorway`.
- Fremmedartslista 2023 doorknockers (`lister.artsdatabanken.no/odata/v1/alienspeciesassessment2023`), genus-membership in the subtree decides inclusion.
- Name resolution requires an exact accepted-name match; anything fuzzier is listed for the user to choose. Never auto-accept a similarity match.

**Show the CSV to the user before continuing** — it is small, and the doorknocker scope is a judgment they own. (GBIF was considered and explicitly dropped for this purpose; the national register is authoritative. For another region, write an adapter that produces the same CSV columns.)

If sources are nb.no links rather than files, the downloader in `sources/nb.no/` and `tools/ocr_pdf.py` run first.

## Phase 0b — extract each source's section ONCE (do not skip)

The single biggest cost in this pipeline is agents re-reading whole books. In the shrew run, ten agents each ran `pdftotext` over a 200–300 page PDF and hunted for the right section: roughly 165k tokens per agent, ~1.6M for the run, to read five books ten times.

Do the extraction **once per source, in the orchestrator**, and hand each agent a small file:

1. `pdftotext -layout` the whole book once to a working file.
2. Find the section by searching for the taxon's scientific and vernacular names, then **verify the boundaries yourself** — read the first and last page of the candidate range and check the neighbours (in the shrew run, one range's last page was a different family, and dense keyword hits in back matter were index entries in every book).
3. Write the bounded section to `<source>.<taxon>.txt`, with a header line recording the PDF page offset so the agent can cite printed page numbers and go back to the PDF for figures.
4. Give the agent **that file**, plus the PDF path only for vision passes on plates.

A 14-page section is ~10k tokens instead of ~150k. The agent still owns every judgment; it just stops paying to find the pages. Same file serves the digitize agent and, later, its auditor.

Other cost controls:
- **Keep agent briefs short.** The rules live in the skills the agent loads — never restate them in the brief. In the shrew run every brief repeated the same ~600-token rule block ten times over; the brief should carry only what is run-specific: source path, section file, species CSV, output paths, and the specific judgment calls flagged for that source.
- **Markdown until the end.** Only the final merged key's companions become PDFs. Source-key companions stay `.md` — they are working documents that the merge reads and the user rarely opens.
- **Vision only where it pays**: comparison plates and figures with three or more arrowed labels. Not every illustration.
- **One agent per source, not per phase, when the key is small.** For a handful of species, run the audit in-session instead of spawning a second agent per source — the audit's value is entering fresh, which a different context window already provides.
- **Merge in-session for small keys.** Spawning agents to merge 7 species across 5 sources costs more than doing it directly.

## Phase 0c — harvest every source's claims (do not skip)

Spin up one `clavis-harvester` agent per taxon per source (Agent tool, subagent_type `clavis-harvester`), each writing `<source>/work/claims/<taxon>.jsonl`; then merge with `harvest-claims/scripts/check_claims.py` into `<source>/work/claims.jsonl`. Harvesters never see a key or another source, and the digitizer that follows is a different agent: the one who lists the claims is not the one who encodes them, and neither is the one who audits. This is the inventory everything downstream is measured against: the digitizer scores from it and writes provenance, the audit checks the key against it, the final gate requires every claim accounted for. The harvest jobs are independent per taxon and per source; run them in parallel where the harness allows.

## Phase 1 — one key per source, via agents

Spin up **one `clavis-digitizer` agent per source document** (Agent tool, subagent_type `clavis-digitizer`). Every agent you spawn, here and in every other phase, gets `model` set to the run's model; never leave it unset, and never a model above the run's (no Fable). One agent per source is not just parallelism — it *enforces source independence*: an agent that has only read Hofmann cannot borrow Gibson's bins.

Each agent's brief:
- Its **pre-extracted section text file** (Phase 0b) — not the whole PDF; the PDF path is given only for vision passes on plates.
- **Page bounds are a hint, not a fact — say so.** Locate candidate pages by searching the extracted text for the taxon's names, but tell the agent to verify the boundaries itself and extend if the section bleeds. In the shrew run every one of the orchestrator's ranges was slightly wrong, and worse: dense keyword hits in a book's *back matter* were index, glossary and literature entries in all three books where they appeared. Never assert "there is back matter with tracks/skulls at pages X" from keyword density; say "check whether anything usable exists there".
- **A unique scratch path per agent.** Concurrent agents overwrote each other's working files in the shrew run when they defaulted to the same scratchpad name. Give each agent its own directory or filename prefix.
- Ask for a `.generator.py` alongside the key — a rerunnable build script makes later fixes cheap and shows the reasoning.
- Scope: only CSV species, but coverage documented **both ways** (what the source covers beyond the list; which CSV species it lacks).
- Independence: metadata from its own source only; co-located Clavis files are sources, not templates.
- Its source's `claims.jsonl` from Phase 0c. Every statement the agent writes must name the claim ids it rests on (`provenance.jsonl`, format in `harvest-claims/references/claim-schema.md`); every claim it does not encode goes in `skipped.jsonl` with a reason.
- Deliverables: key JSON + provenance + skipped + decisions + character-audit + coverage docs, in the source's directory.

Agent management: **never TaskStop a working agent without first having it write its complete state to disk** — killed agents are unrecoverable and the reading work is lost. If a session limit approaches, checkpoint every agent first.

An existing Clavis file (e.g. an artfakta download) is one of the sources — it skips Phase 1 untouched; its couplet decomposition happens inside the merge.

## Phase 2 — audit every draft

One `clavis-auditor` agent per key (or in-session for small keys); corrected output as new versions, originals untouched. The auditor gets the key, the source, and the source's `claims.jsonl`, `provenance.jsonl` and `skipped.jsonl`. Its Phase 1 includes the claims audit (`harvest-claims/scripts/claims_vs_key.py` in exact mode), and its Phase 5 loop does not end until the verifier passes and the claims audit reports zero unsupported statements and zero unaccounted claims. No key enters the merge unaudited.

## Phase 3 — merge

`merge-clavis-keys` with all audited keys + the CSV. That skill owns: equal weighting, name aliasing, couplet resolution, character/state reconciliation, hierarchy (depth decided from species-per-group counts, reported not asked) + vernacular names, coarsening, cleanup, and the verification gates (verify.py, bin continuity, zero-loss round-trip, redundancy report, geography-never-sole-discriminator, two-way coverage).

## Metadata conventions (decide once, apply to all sources)

- **`geography`** on a *source* key is that source's own coverage (a European field guide is "Europa" even when the key is trimmed to Norwegian species). On the *merged* key it is the species list's geography ("Norge").
- **`license`** is not in the sources — it is the licence of the dataset you are producing, so it is a project decision, not a per-source reading. State one licence in the brief so agents don't each invent one (the rodent and shrew keys ended up with three different spellings of CC BY 4.0 plus one rights statement). Use the full URL form.
- Neither field may be copied from another key in the folder.

## Phase 4 — the gate, then deliver

The run is finished when every gate below passes on the final key. When one fails, fix the cause (in the generator, the merge mapping tables, or the source key, whichever owns it), re-run every gate, and repeat. Do not report a failed gate to the user as a result; a failed gate is work left to do. Stop only when all pass, or when the only remaining findings are claims on the skipped list with a reason, or taxon pairs no source separates, both of which are reported as source limits with the evidence.

1. `tools/verify.py` on the final key: PASS, no violations.
2. `check_bins.py`: every numeric scale gapless and overlap-free.
3. Per source: `claims_vs_key.py --provenance --skipped` on the audited source key: 0 unsupported statements, 0 unaccounted claims.
4. Merge round-trip (`roundtrip.py`): every source statement survived, narrowed, or deliberately removed; zero silent losses. Together with gate 3 this makes every claim in every source traceable into the final key or onto a documented list.
5. Redundancy report: for every pair of species the number of separating characters; pairs with zero are listed as source limits, with the sources checked.
6. Geography: no pair separable only by occurrence, or the dependence is documented.
7. Two-way coverage against the species list.

8. Tokens and cost: `tools/token_report.py --since "<work/run-start.txt>" --until "<now>" --match "<sources folder name>" --out <deliverables>/tokens.md`. It sums every transcript of this run, orchestrator and sub-agents, from Claude Code's logs and prices them. Put the total tokens, the cost, and the wall-clock time in the final report next to the gate numbers. On another harness, report the same four numbers (input, cache write, cache read, output) from whatever that harness logs.

Write the gate results, with the numbers, at the top of the final report. A reader must be able to see that the key was measured, not just produced.

Send the user the key file itself plus the companion PDFs. Report in plain language: what was built, what was decided along the way and why, what the key cannot do (pairs no source separates, species no source covers) — stated as source limits, with which kind of seventh source would fix them.

## Reporting style (corrections from the rodent run)

- No jargon, no invented step numbers or internal labels; say what happened in words.
- Report decisions with their reasoning at the moment they're made; don't ask the user to confirm what the pipeline can decide.
- When the user asks "where is it" — the deliverable should already have been sent.
