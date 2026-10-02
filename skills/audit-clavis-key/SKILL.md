---
name: audit-clavis-key
description: Audit and correct a draft Clavis identification-key JSON against its source material. Domain-agnostic and language-agnostic. Runs deterministic structural checks (frequency-rule shapes, ID integrity, leaf-vector discriminability, statement validity) and model-driven semantic checks (sibling-state disjointness, quantitative-character anchor presence, source-coverage spot check), then writes fixes. Use after `digitize-clavis-key` has emitted a draft, or when a user asks to review, verify, or correct an existing Clavis file. Enters fresh — does not generate new content from scratch, only finds violations and patches them.
license: MIT
compatibility: Python 3.11+. Needs tools/verify.py from the repository root. No network.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Audit a Clavis identification key

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant. Deleting is the user's call, even if a plan he approved said "replaces" or "absorbs".


This skill reviews a Clavis JSON file for correctness against its source. It enters with no extraction commitments to defend — its only job is to find violations and fix them. The companion skill `digitize-clavis-key` produces the draft; this skill is the gate before the file ships.

The skill is **domain-agnostic and language-agnostic**. It works on a Norwegian flora, a Spanish bird-song guide, a Mandarin mineral key, a Word document on potsherd typology — same procedure. All checks operate on the structure of the JSON or on operational predicates over real specimens, never on regex patterns over specific words.

## Inputs to gather (ask only if missing)

- **Path to the Clavis JSON** under audit.
- **Path to the source material** (PDF, images, Word doc, plain text).
- **Path to the decisions document** (`<output>.decisions.md`) if one exists.
- **Path to the character-audit table** (`<output>.character-audit.md`) if one was produced during digitization.

## Procedure

The audit runs five phases. Phase order matters: deterministic checks come first because they are cheap and catch bugs that block higher-level analysis. Do not skip phases.

**Language note.** Every companion this skill produces (`<output>.audit-findings`, `<output>.coverage`, the updated `<output>.character-audit`, and any updates to `<output>.decisions`) must be written in the **same language as the source key**. The companions are for the source's domain experts, who can only verify the audit in their own language. Read the language code from the JSON's `language` field. Section headings and prose go in the source language; Clavis technical terms (state names, character titles) stay verbatim as they appear in the JSON.

**Deliverables ship as PDF, not Markdown — but only at the very end.** Throughout Phases 2–5, keep the companions as Markdown so you can edit them, append rows, update sections after fixes, and re-read them easily. The PDF conversion is a single step at the end of Phase 5, after the verifier has signed off on the corrected JSON.

The conversion script is at `scripts/md_to_pdf.py` in this skill's directory:

```
python3 /path/to/audit-clavis-key/scripts/md_to_pdf.py <input>.md <output>.pdf
```

It depends on `reportlab` and `markdown-it-py` (Python) plus Liberation Serif/Sans + Noto Sans Mono (system fonts). The skill's final cleanup step:

1. Convert every `<output>.<kind>.md` (decisions, character-audit, audit-findings, coverage) to the matching `.pdf`.
2. Leave the `.md` originals in place and say they are now redundant — the user removes them if he wants to.
3. Confirm: shipped artefacts are the corrected JSON plus the four PDFs.

### Phase 1: Run the deterministic verifier

Run the verifier, `tools/verify.py` at the repository root (two levels above this skill folder), on the JSON. It checks:

1. JSON parses.
2. Required schema fields present at top level.
3. ID prefixes match convention (`taxon:`, `character:`, `state:`, `statement:`).
4. UUIDs are unique across the file (no two taxa, characters, states, or statements share an ID).
5. Every `statement.taxon`, `statement.character`, `statement.value` references an existing entity.
6. Every `statement.value` is a state of the character it cites (no cross-character state references).
7. Every statement frequency is a number in `[0, 1]`. Graded values such as `0.95`/`0.05` are valid and **must not be rounded to `0.5`** — they carry how often the taxon shows the value.
8. Every answered `(taxon, character)` group leaves at least one value reachable (some frequency > 0). The confident/uncertain shapes are house convention, reported as warnings rather than violations, so deliberate graded encodings survive.
9. State titles are unique within a character (in every language present).
10. State titles are unique *within* a character (two identical labels in one menu are unpickable). Character titles across the file need **not** be unique — characters are identified by id, and a matrix key has no branches, so a trait asked at several points with different state sets is correctly named after the trait each time.
11. Inheritance conflicts: no character is stated on both an ancestor and any of its descendants. A parent's statement holds for all descendants; a descendant restating it makes the key invalid.
12. Discriminability: build per-leaf full-character-vectors with inheritance; no two leaf taxa have identical vectors.

Then the claims audit, when the source has a `claims.jsonl` (it always does inside `build-clavis-key`):

```
python3 <repo>/skills/harvest-claims/scripts/claims_vs_key.py claims.jsonl KEY.json --provenance provenance.jsonl --skipped skipped.jsonl --out KEY.claims-audit.md
```

Direction A lists statements with no claim behind them; direction B lists claims that reached neither a statement nor the skipped list. Both are findings for Phase 5. A key without provenance (made before claims existed) gets the worksheet mode of the same script, and you fill in the verdicts yourself before continuing.

If check 11 fails, `scripts/fix_inherit.py IN.json OUT.json` repairs it mechanically: the ancestor's statement moves onto every child that doesn't state the character itself, and the script aborts unless every leaf's effective values are bit-for-bit unchanged.

### Phase 1b: Convention checks (cheap, deterministic)

Run these before the semantic phases; each was a real defect that shipped once:

- **Bin continuity** — `scripts/check_bins.py KEY.json` parses every quantitative state label and reports gaps ("20–50 mm" followed by "over 100 mm" strands every value between 50 and 100 with no answer) and overlaps. Exact-count states ("3", "4 par") are atomic, not bins, and are skipped.
- **Notation consistency** — one glance over the state labels: ratios must all be percent (no fractions/multipliers mixed in), one unit per quantity across the key, digits not number words, one capitalization style, the "under X / over X–Y / over Y" bin form. See the digitize skill's Label conventions.
- **Non-committal groups** — a taxon asserted with frequency > 0 on *every* state of a character says nothing: no answer can ever exclude it, so the group is dead weight and often marks a character that cannot really be answered for that taxon. List them; if a character is non-committal for most taxa, propose removing it.
- **Duplicate characters** — two characters whose statements induce the same partition of the taxa may be one observable trait encoded twice (this happens after merges and couplet-splitting). Identical partition is *evidence*, not proof — check whether the two titles describe the same observation before merging them.
- **No source tags or bookkeeping in character titles.**

These are universal — no language assumptions. If any check fails, fix the structural bug before continuing. Most are mechanical (renaming, deleting duplicates, repairing assignments).

### Phase 2: Sibling-state disjointness audit

Tests A and B and the required output table are in `references/phase-2-disjointness.md`. Read it when you reach this phase.

### Phase 3: Quantitative-character anchor audit

Procedure in `references/phase-3-anchors.md`. Read it when you reach this phase.

### Phase 4: Source-coverage spot check

Procedure, including the geographic-occurrence check, in `references/phase-4-source-coverage.md`. Read it when you reach this phase.

### Phase 5: Apply fixes and re-run

For every violation found in phases 1–4, apply the fix. The shape of the fix depends on the phase:

- **Phase 1 fixes** are mechanical: rename, deduplicate, repair assignment.
- **Phase 2 fixes** depend on which kind of overlap was found:
  - *Range/superset*: re-bin into a true partition; re-encode boundary taxa with paired uncertain frequencies.
  - *Bundled distinguishables*: split the state into atomic states; re-encode any taxon whose source admits the bundled values with paired uncertain frequencies.
  - *Cross-axis overlap*: **split the character itself** into one new character per axis. Each original state decomposes into one or more (new_char, new_state) assignments; re-encode every taxon's assertion accordingly. The `refine-clavis-key` skill's `scripts/apply_character_split.py` performs this mechanical split given a decisions JSON; use it instead of hand-editing.
- **Phase 3 fixes** rewrite state titles to add numeric ranges; the underlying assignments don't change unless re-binning shifts boundary cases.
- **Phase 4 fixes** add new characters and emit statements for them across all relevant taxa, or document the skip.

After applying fixes, re-run Phase 1 in full: the verifier and the claims audit. Any finding means another round of fixes. The audit is complete only when the verifier passes and the claims audit reports 0 unsupported statements and 0 unaccounted claims, and you report those numbers.

If the key was built by a generator script (`.generator.py`), either apply the fixes *through* the generator so it stays authoritative, or rename it to mark it stale (`.v1-generator.py`) — a generator that silently emits the pre-audit key is a trap for whoever reruns it later.

Update the decisions document at `<output>.decisions.md` to record any fixes made — bin boundaries adjusted, states split, characters added, source contradictions flagged.

## Verifier template

Run `tools/verify.py` (repository root) on the target JSON file. Flags: `--collisions-warn` when the source genuinely cannot separate a pair; `--without REGEX` for the geography re-check (collisions with matching characters removed, reported as warnings). The script is universal — no language or domain knowledge baked in. It performs the structural checks listed in Phase 1.

If a check fails, the script prints which `(taxon, character)` group or which entity is implicated. Fix in the source generator (or directly in the JSON if the generator script is gone) and re-run.

## What audit-clavis-key does NOT do

- It does not generate new taxa, characters, or states from the source — that is the digitize skill's job.
- It does not change the language or domain framing — it only fixes violations.
- It does not skip the predicate-disjointness or quantitative-anchor audit because they "look fine" — those phases are required output. Spot-checking by eye is the failure mode this skill is designed to prevent.

## Failure modes this skill catches that the digitize phase typically misses

- **Range/superset state overlaps** like *"4"* sitting next to *"5 or fewer"* in a stamen-count character.
- **Bundled distinguishable values** like *"yellow or red spots"* sitting next to *"red spots"* in a marking character.
- **Cross-axis bundled characters** like a "Body coloration" character mixing colour states (*green*, *brown*) with pattern states (*spotted*, *with two prominent spots*) — Test A flags this as overlap; the fix is a character split, not a state split.
- **Relative-only quantitative bins** like *small/medium/large* with no cut points.
- **Missing characters** the source describes for multiple taxa with different values but the digitization phase didn't notice.
- **Frequency-rule corner cases** introduced by late-stage edits (a typo'd state key that resolves to all-zero frequencies).
- **Discriminability collisions** caused by hoisting a character too high: a trait set on a parent then holds identically for every descendant, and two leaves that differed in the source end up with the same vector.
