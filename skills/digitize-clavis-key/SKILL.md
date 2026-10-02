---
name: digitize-clavis-key
description: Turn one source's claims inventory (from harvest-claims) into a Clavis identification key for that source. Domain-agnostic and language-agnostic. Designs single-trait characters with determinable states, keeps every measurement as a numerical character with [min, max] per taxon, scores statements from the claims by script with provenance for every statement, and writes a decisions document. Use when the user asks to digitize a key, build a Clavis file from any identification reference, or convert a scanned or printed key into the Clavis format. Hand off to audit-clavis-key afterwards.
license: MIT
compatibility: Python 3.11+. Needs the source's claims.jsonl from harvest-claims and tools/verify.py from the repository root. No network.
metadata:
  author: Artsdatabanken
  version: "2.0"
  pipeline: clavis-pipeline
---

# Digitize a source into Clavis JSON

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant.

Clavis is a JSON schema for identification keys (https://github.com/Artsdatabanken/Clavis): **taxa** (what is identified), **characters** (one observable trait each), **states** (the answers of a categorical character), and **statements** (taxon × character × value with a `frequency` in 0–1). A character's `type` is `exclusive` (one state at a time), `non-exclusive` (several states can hold at once: habitats, signs) or `numerical` (`min`, `max`, `stepSize`, `unit`; a statement's `value` is the taxon's `[min, max]`).

This skill works from the **claims file** of one source, not from the book. The harvester already read every page and wrote one line per assertion with quote and page. Your job is design and judgment: which traits become characters, which values become states, what is a measurement, what is skipped and why. Scoring is a script. Open a source page only when a claim is ambiguous and the quote does not settle it.

This skill is domain-agnostic and language-agnostic, and produces a **draft**. `audit-clavis-key` enters fresh afterwards and only finds violations.

## Inputs to gather (ask only if missing)

- **Claims**: `work/<source>/claims.jsonl` from `harvest-claims`. If it does not exist, run `harvest-claims` first; never digitize without it.
- **Taxon list**: the species CSV that scopes the key (`scientificName` column). Taxa in the claims that are not on the list are reported in the coverage note, not encoded.
- **Language code** of the source, e.g. `nb`, `en`, `de`.
- **Output path**: `work/<source>/<source>.<taxon-group>.json`, companions next to it.
- **Metadata**: title, geography and licence come from the brief; `externalServices` only when the source provides external ids. A Clavis file in the same folder is an independent source, never a template.

## Step 1: Read the claims, group by trait

Load the claims and list the distinct normalized traits with their values per taxon (a scratch script in `work/<source>/scratch/`; never in the sources folder). This table is your material. For each trait decide one of:

- **Character** (two or more taxa, different values): categorical or numerical.
- **Skip** with a reason (`skipped.jsonl`): `not-observable` (the harvester marked it, or you judge it: age, litter size, diet), `no-variation`, `duplicate`, `out-of-scope`.

A trait only one taxon is described with is a valid character when the other taxa are known not to have it: a flat tail separates the beaver from every species the source describes with a round tail. So first look for the same trait under other wordings for the other taxa (round tail, long thin tail) and make it one character with several states. If the source says nothing about the trait for the other taxa, keep the character anyway and score only the taxon that has it: the merge removes a character no answer can ever rule a species out with, and lists it. Never invent a "no" for taxa the source is silent about.

Every claim ends up in exactly one of those two places. The claims audit at the end proves it.

## Step 2: Design the characters

The design is a JSON file (`design.json`, format in `scripts/score_claims.py`), not an assignment map. For each character:

- **Title**: what the user observes, in the source language. No source names, step numbers or bookkeeping in titles. Duplicate titles are legal (a trait asked twice with different state sets); never disambiguate by position in the key.
- **`traits`**: the normalized claim traits that feed it. Several wordings for one observable go on one character.
- **Numerical** for every measurable quantity the source gives numbers for: length, mass, count on a scale, ratio, duration, angle. One unit per quantity across the key, ratios in percent. No bins, no cut points: `score_claims.py` writes each taxon's `[min, max]` as the union of its claims. A quantity the source only describes in words ("small", "long") is not numerical; it is a categorical character with the words as states, flagged later as relative; keep it if it is the only separator, else skip.
- **Categorical** otherwise. The states must form a partition of the asserted values (Protocol 1 in `references/partition-protocol.md`): no overlap, no gap. Each state lists `values`: every claim wording that means this state (`hvit`, `hvitaktig`, `white`). Exact wording after normalization; the script does not guess.
- **Exclusive or non-exclusive**: habitats, signs, foods, "occurs in" lists are non-exclusive. Everything a specimen shows one of at a time is exclusive.
- **Determinable** (see `determinability-pass`): a state is something one person with one specimen and the guide can pick, without a second specimen or experience. Comparatives ("darker than X", "larger") become absolute terms when the source allows, or are skipped with `comparative-unresolved`; shades collapse to a small palette ("rødbrun" and "rød" are one state unless two taxa are separated by that difference and a user could see it); bundles ("brown or grey") never become a state, they become two statements.
- **Order** the characters by field-answerability: seen at a glance, then measurements, then habits and habitat, then in-hand details, then tracks and signs, then internal and microscopic.

Taxa: a **flat list** of the species on the CSV, scientific name as in the list, vernacular name if the source gives one. No hierarchy; the merge builds it from the register and does the hoisting.

Label conventions: one unit per quantity, ratios in percent, digits not number words, one capitalization style.

## Step 3: Score

```
python3 scripts/score_claims.py work/<source>/claims.jsonl design.json --out scored.json --residue residue.md
```

The script matches claims to characters by trait and to states by `values` or containment, writes numerical ranges as unions, takes frequencies from `harvest-claims/references/frequency-table.json` (always 1, usually 0.9, sometimes 0.4, rarely 0.1; the alternative value in a two-value claim gets the secondary number), and writes provenance for every statement. Exclusive characters get no zero-frequency statements: zero is implied for every unstated sibling state.

Read `residue.md`. Each line is a claim the script could not place. Fix the design (add a state, add a wording to `values`, add a trait), or skip the claim with a reason. Re-run until the residue holds only skipped claims. Never hand-write a statement the script could have produced.

## Step 4: Generate the key

A short generator script in `work/<source>/` (keep it; it makes fixes cheap) that reads `scored.json`, adds the metadata (`$schema`, `identifier` as a fresh UUID, `lastModified`, `language`, `title`, `license`, `geography`, `externalServices`, `persons`, `mediaElements`), and writes the key, `provenance.jsonl` (from `scored.json`, plus any statement you added by hand with its claim ids) and `skipped.jsonl`.

Then, until both are clean:

```
python3 <repo>/tools/verify.py KEY.json
python3 <repo>/skills/harvest-claims/scripts/claims_vs_key.py work/<source>/claims.jsonl KEY.json --provenance provenance.jsonl --skipped skipped.jsonl --out claims-audit.md
```

Zero violations, zero unsupported statements, zero unaccounted claims. A claim you decide not to encode goes on the skipped list with its reason; it is never ignored.

## Step 5: Companions and hand-off

Write the decisions document (`references/decisions-document.md`) and the two-way coverage note (species on the list the source lacks; taxa the source covers beyond the list) in the source language, as Markdown. Then invoke `audit-clavis-key` with the key, the claims, the provenance, the skipped list and the decisions document. The digitization is complete when the audit signs off.

## What stays out

- Reading the whole source again: the claims are the source's content. The audit re-reads sampled claims against their quotes, not the book.
- Hierarchy and hoisting: the merge does both from the register.
- Zero-frequency statements on exclusive characters.
- Vote shares or made-up percentages: frequencies come from the table.
