---
name: audit-clavis-key
description: Audit and correct a draft Clavis identification-key JSON against the claims harvested from its source. Domain-agnostic and language-agnostic. Runs the deterministic verifier and the claims audit (every statement traces to a claim, every claim reached the key or was skipped with a reason), then checks state partitions, numerical characters and determinability, and loops on fixes until every check is at zero. Use after digitize-clavis-key, or when a user asks to review, verify or correct an existing Clavis file. Enters fresh; never generates content from scratch.
license: MIT
compatibility: Python 3.11+. Needs tools/verify.py and the harvest-claims scripts from the repository. No network.
metadata:
  author: Artsdatabanken
  version: "2.0"
  pipeline: clavis-pipeline
---

# Audit a Clavis identification key

**Never delete or overwrite the user's files.** Corrected output is a new file (`<key>.audited.json`), companions alongside.

You enter with no extraction commitments to defend. The digitizer designed and scored; you find what is wrong and fix it, measured against the claims. All checks operate on the JSON, the claims, the provenance and the quotes, never on regex over specific words of one language.

## Inputs to gather (ask only if missing)

- The Clavis JSON under audit.
- `claims.jsonl`, `provenance.jsonl`, `skipped.jsonl` of its source (`harvest-claims`). A key without them (made before claims existed) first gets the no-provenance procedure in `harvest-claims` ("did we miss anything"), which produces the claims and a worksheet; then this audit runs on the result.
- The decisions document and `design.json`, if present.
- The source text and figure crops under `work/<source>/`, for the few claims whose quote does not settle a question.

**Language.** Companions (`<key>.audit-findings.md`, the updated character-audit table) are written in the key's language, for its domain experts. Markdown throughout; PDF only at the end of the whole run and only when the converter's dependencies are present.

## Phase 1: Deterministic checks (scripts, no judgment)

```
python3 <repo>/tools/verify.py KEY.json
python3 <repo>/skills/harvest-claims/scripts/claims_vs_key.py claims.jsonl KEY.json --provenance provenance.jsonl --skipped skipped.jsonl --out KEY.claims-audit.md
python3 scripts/check_bins.py KEY.json
python3 scripts/coverage_test.py KEY.json claims.jsonl provenance.jsonl --out KEY.coverage-test.md
```

- `verify.py`: parse, required fields, id integrity, references, state belongs to its character, frequencies in [0, 1], no dead groups, no overriding, leaf discriminability, numerical characters well-formed (unit, min ≤ max, one range per taxon, ranges inside the character range). Convention warnings only on exclusive characters.
- Claims audit: direction A (statements without a claim; a numerical statement whose range does not cover its claim) and direction B (claims that reached neither a statement nor the skipped list). Both are findings.
- `check_bins.py`: numerical characters have a unit and valid ranges; any leftover bin labels are contiguous.
- `coverage_test.py`: Protocol 1 Test B from the provenance: every claim maps to a state by wording or containment, or is listed as "mapped by judgment" for you to confirm; numerical claims outside their statement's range are defects.

If overriding is found, `scripts/fix_inherit.py IN.json OUT.json` repairs it mechanically.

## Phase 2: Partition and type (judgment, on the flagged rows only)

Read `references/phase-2-disjointness.md`. For every categorical character, Test A on every sibling pair (overlap: range/superset, bundled, cross-axis) and the "mapped by judgment" rows from `coverage_test.py` (is the state a fair reading of the claim? "små runde ører" scored as "sticks clearly out of the fur" is not). For measurements: read `references/phase-3-numerical.md`; any measurable trait encoded as categorical bins is a defect, as is a categorical character whose states all parse as numbers.

## Phase 3: Determinability (judgment, on the flagged rows only)

```
python3 <repo>/skills/determinability-pass/scripts/flag_undeterminable.py KEY.json --out KEY.determinability.md
```

For every flag: can one person, with one specimen and the guide, no comparison specimen and no experience, pick the state? Comparatives become absolute terms (from the claims' numbers or wording) or the claim is skipped with `comparative-unresolved`; shades merge to a palette a user can name; bundles split; relative words without numbers stay only when nothing else separates the taxa, with a line in the findings. The determinability pass runs again on the merged key; the fewer flags you leave, the less it has to do.

## Phase 4: Fix, re-run, loop

Apply every fix through the generator and `design.json` (so `score_claims.py` reproduces the key) or, when the generator is gone, directly in the JSON with `provenance.jsonl` and `skipped.jsonl` kept in step. State splits and merges can use `refine-clavis-key/scripts/apply_state_splits.py` and `apply_state_merges.py`; character splits `apply_character_split.py`.

Then Phase 1 again, in full. Any finding is another round. The audit is complete only when the verifier passes, `check_bins.py` is clean, `coverage_test.py` has no numerical defects, and the claims audit reports **0 unsupported statements and 0 unaccounted claims**. Report those numbers.

Write `<key>.audit-findings.md`: every finding, the fix, the numbers before and after. Update the decisions document with what changed.

## What this skill does not do

- Re-read the book. The claims are the source's content; a quote decides, and a page is opened only when the quote cannot.
- Generate new characters from the source. If the claims audit shows a claim the key lacks and the design should have a character for it, add it through the design and the script; that is still the claims' content, not new reading.
- Build hierarchy, hoist, or merge. The merge does those.
- Skip the partition or determinability review because things look fine. The flagged rows are the required output.
