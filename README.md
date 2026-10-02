# Clavis pipeline

Turn printed identification keys, field guides, spreadsheets and online keys into [Clavis](https://github.com/Artsdatabanken/Clavis) identification-key files, with AI agents doing the reading and deterministic scripts doing the checking.

This repository contains the pipeline only: instructions for the model, the scripts those instructions call, and the two agent definitions. It contains no source books, scans, OCR output or draft keys. Bring your own sources.

## Quick start

Give this to your AI agent, whichever one you use:

> Clone https://github.com/Artsdatabanken/clavis-pipeline, read its AGENTS.md, and make a Clavis key for <taxon> from <these files / this folder / these links>.

`AGENTS.md` tells the agent the order of steps, where the scripts are, and the rules. Claude Code users get a smoother path by linking the skills in first (`guides/claude-code.md`). Other harnesses read `AGENTS.md` on their own.

Sources can be local files (PDF, page images, spreadsheets, existing Clavis files) or online (an nb.no book, a Naturalis or artfakta key). It runs on Linux, macOS and Windows; everything is Python except OCR, which needs Surya.

For the reasoning behind the design, read `docs/clavis-agentic-workflow.md` first. It explains the whole process from book to verified key for readers without a background in biology, keys or computing.

## What is in here

```
AGENTS.md   what any AI agent reads first; CLAUDE.md points Claude Code at it
guides/     one page per harness and model: what is validated, what is reported, the feedback template
skills/     one folder per step; SKILL.md is the procedure, references/ the detail it links to, scripts/ its code
agents/     three agent definitions for Claude Code: harvester (one per source, taxon by taxon), digitizer (one per source), auditor (one per draft)
adapters/   everything that talks to a taxonomy register or national list; NorTaxa is the example
sources/    downloaders and scrapers for particular places material comes from (nb.no, Naturalis, artfakta)
tools/      generic helpers: OCR, verifier, refiner
docs/       the workflow explainer
schema/     the Clavis JSON Schema the output is validated against
```

Generic versus specific: `skills/`, `agents/`, `tools/`, `docs/` and `schema/` know nothing about any provider. `adapters/` and `sources/` are the only places a register or website is named. To run the pipeline in another country, write a taxonomy adapter and a species-list script (the contract is in `adapters/taxonomy/__init__.py` and `adapters/README.md`) and, if needed, a downloader for your library. Nothing else changes.

The steps, in the order they run:

| Step | Skill | What it does |
|---|---|---|
| 1 | `build-clavis-key` | Orchestrates everything below for a target taxon and a folder of sources. Species list through an adapter (Norway: NorTaxa plus the alien-species list), one preparation per source, one harvester per taxon per source, one digitizer per source, one fresh auditor per draft, merge, determinability pass, then the gate loop and the cost report. |
| 2 | `harvest-claims` | Prepares a source (text once, each taxon's pages, the figures as crops) and lists every observable claim per taxon with quote and page into `claims.jsonl`; numbers and units parsed, diagnostic traits and look-alike statements marked, duplicates removed. One agent per source. Checks a finished key in both directions: every statement traces to a claim, every claim reached the key or a skipped list. |
| 3 | `digitize-clavis-key` | One source's claims in, one key out. Designs single-trait characters with determinable states and numerical characters for every measurement; a script scores the statements from the claims with provenance; flat taxon list. |
| 4 | `audit-clavis-key` | Fresh agent: verifier, claims audit, range checks, coverage test, then partition, type and determinability review on the flagged rows only; loops on fixes until every check is at zero. |
| 5 | `refine-clavis-key` | Structural cleanup of a key from a transcoder (matrix export, web scrape): couplets decomposed per taxon along its path, duplicate characters merged, bundled states split, bins to numerical characters. |
| 6 | `merge-clavis-keys` | Union first (equal weight per source), one spec file for the concordance and per-source state maps, intersection-first reconciliation with every asserted value kept, ranges unioned, hierarchy from the register, measured location cleanup and coarsening, zero-loss round-trip. |
| 7 | `determinability-pass` | Fresh agent on the merged key: a script flags comparatives, bundles, relative words and over-fine palettes; the agent makes every state answerable by one person with one specimen and the guide; the gate proves no pair lost its last route. |
| 8 | `translate-json` | Adds a language to any JSON file with language-keyed strings. Scripts extract and splice; the model only translates; vernacular names come from registers. |

Each skill is self-contained: the SKILL.md names every script it uses by path relative to its own folder, and every script is plain Python 3 with command-line help.

## Using it with Claude Code

Start Claude Code inside this folder; it picks up the skills and agents from `.claude/` with no setup. Your sources can be anywhere, give their paths. To have the skills available from any folder, link or copy them into `~/.claude/` (`guides/claude-code.md`). Then:

> Make me a key for Soricidae from these books.

Claude picks `build-clavis-key`, which spins up the digitizer and auditor agents itself. To run a single step, name it: "digitize this PDF into a Clavis key", "audit this key against the book", "merge these three keys", "translate this key to English".

## Using it with another framework

Nothing here depends on Claude. A skill is a markdown file plus scripts, and `AGENTS.md` is the entry point most harnesses (Codex, Cursor, Gemini CLI, Aider, OpenCode) read on their own. Only Claude Code has been validated so far; `guides/` tracks the rest, and `guides/TEMPLATE.md` is the form we ask users to send back as a pull request. To run a step by hand in any agent framework:

1. Give the agent `skills/<step>/SKILL.md` as its system prompt or task instructions, unchanged.
2. Give it a shell and the `skills/<step>/scripts/` folder (or `pipeline/` for translate-json), so it can run the scripts the instructions name.
3. Give it the source document (or the key to audit, merge or translate) and tell it where to write.

The two files in `agents/` describe the digitizer and auditor roles in a few paragraphs; use them as the agent's persona, or ignore them and use the skills directly. The one rule that matters when you run several digitizers: each must see only its own source. The independence of the drafts is what the merge step relies on.

The model matters. The pipeline was developed and run with Claude Opus-class models with vision, reading page images directly to catch figure labels that OCR drops. A model without vision will miss those; a much smaller model will make more of the judgment errors the audit step is there to catch. Costs are reported in the workflow document.

## Models and cost

Recommended setup: **Claude Opus 5.5 runs the job, Claude Sonnet 5.5 does every agent's work**, in Claude Code (`guides/claude-code.md`). Measured with that setup, October 2026:

| Material | Taxa | Wall-clock | Tokens (cache read / cache write) | API-equivalent cost |
|---|---|---|---|---|
| five printed field guides (four of them scanned books) and one existing digital matrix key | 24 | 73 min | 172 M / 7.0 M | USD 56 |
| one existing dichotomous key with a glossary, in a Word document | 47 | 46 min | 56 M / 2.6 M | USD 19 |

Also tested: Opus for every agent (no better, three to five times the cost), Sonnet running the job as well (cheaper, but its own wrong calls cost separations), Haiku 4.5 as harvester (not good enough: half the claims, a fifth of its quotes not in the book), Fable 5.1 (far more expensive with nothing here that needs it). Details in `guides/claude-code.md`.

Costs are what the same tokens would cost through the Claude API at list prices on 2 October 2026; prices change, the token counts are what to compare. Almost all of it is input re-read from cache. On a Claude Max subscription several runs fit in a day, so the practical cost per run is a few dollars.

If you run the pipeline with another model or harness, please send what happened (`guides/TEMPLATE.md`, as a pull request): the aim is good keys from as little compute as possible, and a well-described failure helps as much as a success.

## Tools, sources and adapters

`tools/` (generic):

| Script | Purpose |
|---|---|
| `ocr_pdf.py` | OCR stitched page images into a searchable PDF (Surya), with reading-order handling for two-column layouts. |
| `verify.py` | The structural verifier every skill calls: parse, required fields, id integrity, references, frequencies in [0, 1], no dead groups, no overriding, leaf discriminability. `--without REGEX` re-checks with matching characters removed. |

`sources/` (one folder per place material comes from; see `sources/README.md`):

| Folder | Purpose |
|---|---|
| `nb.no/` | Page images from the National Library of Norway, stitched from IIIF tiles, plus crop and rotate (`crop_rotate.py`). |
| `naturalis/` | Naturalis Linnaeus-NG keys: dichotomous keys scraped to PDF, matrix keys scraped and transcoded to Clavis. |
| `artfakta/` | SLU Artdatabanken: the artfakta.se matrix-key API and the SLU key-authoring workbook, transcoded to Clavis. |

`adapters/` (one module per register; see `adapters/README.md`):

| Path | Purpose |
|---|---|
| `taxonomy/nortaxa.py` | Resolve names, get higher classification and vernacular names from NorTaxa. Default; select another with `CLAVIS_TAXONOMY=<name>`. |
| `species-list/norway.py` | Species CSV for a Norwegian taxon from NorTaxa plus the alien-species list. |

Transcoder output is a rough draft. Run `refine-clavis-key` on it, then `audit-clavis-key` if you have the source.

## Requirements

Python 3.11 or newer on Linux, macOS or Windows. `pip install -r requirements.txt` covers the scripts (`python` instead of `python3` on Windows). OCR additionally needs [Surya](https://github.com/VikParuchuri/surya). Text extraction from PDFs uses `pdftotext` (poppler) where available and falls back to `pypdf`.

## Output

Every run produces a Clavis JSON file validated against `schema/Clavis.json`, with measurements as numerical characters (`[min, max]` per taxon), no zero-frequency statements on exclusive characters, and a gate report with numbers: verifier, ranges, claims audit per source, round-trip, redundancy, geography, coverage, tokens and cost. Companions: the decisions record, audit findings, removed characters, round-trip, redundancy and coverage reports. The key is meant as an expert-editable draft; every statement can be traced to a quoted passage. Open it in the [Clavis editor](https://clavis.no) or any viewer that reads the format.

## Sources stay out of this repository

Never commit source material: scanned books, PDFs, page images, OCR text, scraped HTML, or draft keys derived from copyrighted works. `.gitignore` blocks the common file types; check `git status` before every commit anyway.

## Citation

Koch W, Elven H, Finstad AG (2022). Clavis: An open and versatile identification key format. PLoS ONE 17(12): e0277752. https://doi.org/10.1371/journal.pone.0277752

The pipeline itself is presented at TDWG 2026.
