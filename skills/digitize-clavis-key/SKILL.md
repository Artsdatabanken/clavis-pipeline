---
name: digitize-clavis-key
description: Digitize a dichotomous identification key from source material (printed flora, mammal-tracks guide, bird key, fungal monograph, mineral typology, archaeological-artefact key, or any analogous reference) into a Clavis JSON file. Domain-agnostic and language-agnostic. Decomposes combined couplet statements into atomic single-trait characters, deduplicates states, attaches shared traits at the highest applicable internal-node taxon (so parent-level traits aren't repeated on every leaf), and mines descriptions for additional discriminators beyond the printed couplets. Use when the user asks to digitize a key, build a Clavis file from any identification reference, transcribe a printed identification key, or convert a scanned/document key into the Clavis format. After this skill emits draft JSON + decisions doc, hand off to `audit-clavis-key` for verification and correction.
license: MIT
compatibility: Python 3.11+. A model with vision reads figure labels; without vision the text-only path still works.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Digitize a dichotomous key into Clavis JSON

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant. Deleting is the user's call, even if a plan he approved said "replaces" or "absorbs".


The Clavis format is a JSON-based identification-key schema (https://raw.githubusercontent.com/WouterKoch/Clavis/main/Schema/Clavis.json). It separates **taxa** (the things you identify — species, footprint patterns, mineral specimens, artefact types, whatever the source covers), **characters** (single traits — one observable axis each), **states** (mutually exclusive options for a character), and **statements** (taxon × character × state with a `frequency`, any number in 0–1). A character's `type` is `exclusive`, `non-exclusive`, or `numerical`; identification keys normally use `exclusive`, and a taxon that shows several states of one character (variability, a boundary-straddling measurement) gets one statement per state with the frequencies the source supports.

**Measurements have their own character type.** A `numerical` character carries `min`, `max`, `stepSize` and `unit` instead of `states`, and its statements take `value: [min, max]` — the taxon's actual measured range. Prefer this over binning a measurement into states: it keeps the real numbers, removes all bin-boundary questions, and lets the renderer bin for display. Bin into states only when the source itself gives classes rather than measurements.

This skill is **domain-agnostic and language-agnostic**. The next key may be a flora in Norwegian, a Spanish field guide to bird songs, a German monograph on lichens, a Word document on archaeological pottery sherds, a Mandarin key to fungi. The same translation work applies: split bundled prose into atomic characters, hoist shared traits up the hierarchy, and fill in everything the source tells you — even traits the printed couplets don't ask about. Examples in this file rotate across domains and languages on purpose; do not generalize from any single example.

This skill produces a **draft**. After emitting the JSON + decisions doc, hand off to `audit-clavis-key`, which enters fresh and only knows how to find violations. The audit phase is the gate that catches failures introduced during creative extraction.

## Inputs to gather (ask only if missing)

- **Source pages** — image paths, PDF, Word document, or text file. Bound the range with start/end so you don't bleed into the next group. If the user dropped a folder of files, confirm where the target section begins and ends.
- **Claims file** — `claims.jsonl` for this source from `harvest-claims`. If it does not exist, run `harvest-claims` first; do not digitize without it. Every claim is either encoded (and named in `provenance.jsonl`) or skipped with a reason (`skipped.jsonl`). Formats: `harvest-claims/references/claim-schema.md`.
- **Language code** — e.g. `nn`, `nb`, `en`, `de`, `es`. The whole file uses one set of i18n keys — set them all at the same level.
- **Output path** — default to the same directory as the source, named after the group covered (vernacular or scientific name).
- **Existing example file** — only if the user explicitly designates a file as the template, reuse its `externalServices`, `license`, `language`, and `geography` shapes. A Clavis file that merely sits in the same folder is an independent source, never a template — do not carry anything over from it. Metadata comes from the source being digitized: its language, its title, its geographic coverage; `externalServices` empty unless the source provides external IDs.

## Output shape (Clavis schema)

Top-level fields, in the order the example uses them:

- `$schema`: the schema URL above.
- `identifier`: a fresh UUID (no prefix).
- `lastModified`: `YYYY-MM-DD HH:MM:SS` UTC.
- `language`: array of codes, e.g. `["nn"]`.
- `title`: localized object, e.g. `{"nn": "Søterotfamilien (Gentianaceae)"}`.
- `externalServices`: copy from the example file. Don't invent new ones unless the source provides external IDs.
- `taxa`: nested array. Each taxon has `id` (UUID prefixed `taxon:`), `scientificName`, optional `vernacularName`, optional `externalReference`, and optional `children` (array of taxa).
- `characters`: array. Each has `id` (`character:` prefix), `title` (localized), and `states` (array). Each state has `id` (`state:` prefix) and `title`.
- `statements`: array. Each has `taxon`, `character`, `value` (the state ID), `id` (`statement:` prefix), and `frequency`.
- `persons`, `mediaElements`: usually empty arrays unless the source provides them.
- `license`: copy from the example.
- `geography`: localized name object.

## Protocols (apply to every character before emitting JSON)

These two protocols are the most-often-violated parts of this skill. They are language-neutral, domain-neutral, format-neutral. Both produce required artifacts before the JSON is written. Skipping them is the failure mode the audit skill is designed to catch — but doing them here is cheaper than discovering violations later.

Protocol 1 (atomic states: partition both ways) and Protocol 2 (quantitative-character anchors) are in `references/partition-protocol.md`. Read that file before extracting characters; it defines the partition tests, the anchor rules, and the artifacts each requires.

## The key is a matrix, not a path

Clavis keys have no branches. Every character is an independent question; answering one only filters the candidate set. The user answers whichever characters they can observe, in any order, and any subset is valid — there is no “right” question to pick and no wrong turn. Consequences:

- **Duplicate character titles are legal and often correct.** Characters are identified by `id`. A trait asked at two points with different state sets (tail length broadly, tail length finely within one group) is correctly named after the trait both times. Never disambiguate a title by its position in the key (“Tail length (Apodemus)”) — that labels the question by where it sits instead of by what the user observes, and leaks the answer.
- **Redundancy is a feature.** Multiple characters separating the same pair give the user multiple routes; do not prune a character merely because another already separates the same taxa.

## Label conventions (apply before emitting JSON)

Each of these was a correction on a real key — apply them from the start:

- **Ratios in percent, always.** Never mix fractions, decimals and multipliers (“0,2–⅓ ×”, “over ½”). Write “under 20 %”, “over 20–50 %”, “over 100 %”.
- **One unit per quantity across the whole key.** If lengths are in mm, every length is in mm — never one character in cm with decimals beside others in mm.
- **Digits, not number words**, in state labels (“3 / 4”, not “Tre / Fire”).
- **Bin convention: “under X” · “over X–Y” · “over Y”** (in the key's language). Adjacent bins must agree on which bin the boundary value falls in. The single point X left uncovered by “under X / over X–Y” is harmless for a continuous measurement; an overlap gives the user two valid answers and is a defect.
- **One capitalization style** for state labels across the key.
- **No provenance in names.** Character titles never carry the source, a step number, or internal bookkeeping.

## Character order = field-answerability

The order of `characters` in the file is the order the user meets. Order by how much access to the subject each question requires, easiest first. For animals: external features seen at a glance (colour, markings, tail, ears) → measurements → habitat and habits → subject-in-hand details → tracks and signs → internal/microscopic (teeth, skull). Analogous ladders exist in every domain (naked eye → hand lens → microscope → chemistry). Never ship in extraction order.

## Reading the source

Procedure in `references/source-extraction.md`. Read it before opening the source: how to extract the bounded text once, and how to read figure labels with vision.

## Building the taxa tree

The hierarchy depends on the domain. Most biological keys nest family → genus → species → subspecies, but the skill works for any tree-shaped grouping the source uses.

1. Identify the **root taxon** — the top-level grouping the source covers. Use whatever name the source gives in `scientificName`, and the vernacular in `vernacularName` if the source provides one.
2. Walk intermediate groupings in source order, nesting each as children of their parent. Authority strings, type designations, and other parenthetical qualifiers stay inside `scientificName` as written.
3. Walk leaf taxa in source order under each grouping.
4. Sub-types (subspecies, varieties, sub-forms, sub-classes) are children of their parent only if the source distinguishes them in the key. Otherwise they belong in the description text.
5. External references (e.g. catalogue IDs, taxon keys, accession IDs) are added **only if the source provides them**. If an empty/template Clavis file in the same folder defines `externalServices`, carry that block over verbatim even if no taxon in this file uses it.

## Extracting characters and states

### Rule 1: One character per trait

Read every couplet and every taxon description. For each prose sentence that contains multiple traits, split it into one character per trait. Maintain a running list of `(character, [states])` as you read. **Reuse a character whenever the same trait recurs at any depth of the key.** Two couplets at different points in the key that both ask about the same observable trait collapse into one character with all observed states. State labels are deduplicated by **meaning**, not exact wording — pick the clearest phrasing the source uses; don't paraphrase further than necessary.

Compound source phrases that bundle two trait axes into one description must be split into two characters. Example: a description like "*dark-blue with light stripes*" combines colour (dark-blue) and striping (with light stripes) — that's two characters, not one combined state.

### Rule 2: States must be atomic from the observer's perspective

A state represents **one** thing a user can observe on a specimen they have in front of them. The user with a specimen in hand sees one value; they don't know whether that value is the dominant or the rare form for a given taxon, and they shouldn't have to guess. The state list is the menu they pick from — every observable value needs its own entry, and only values the user can actually tell apart deserve separate entries.

This rule is enforced by **Protocol 1** (`references/partition-protocol.md`). Apply the disjointness predicate to every sibling-state pair, and document the result in the required audit table. Do not emit JSON until the audit is complete.

When the source admits multiple values for a taxon (whether by listing alternatives, marking one as uncommon, or giving a range that crosses your bin boundaries), keep the states atomic and encode the taxon with **paired uncertain frequencies** on those atomic states (see Frequency convention).

### Merging near-identical state values

Two source terms that name the same observable thing — different words for the same shade, the same shape, the same texture — should collapse into one state with " / " between the labels. The discriminating test from Protocol 1 still applies: if a careful observer cannot reliably tell A from B on a real specimen (because they're synonymous or differ only in degree below perceptual threshold), merge them. If they're synonymous in the source's vocabulary but visually identical, merging is correct.

When in doubt, keep separate. The cost of a wrong merge is losing identification resolution that the source provided. The cost of a wrong split is harder for a user to choose, but the audit pass will surface it.

When merging, transfer frequencies correctly: for each taxon, the merged state's frequency is the *maximum* of the input states' frequencies on that taxon.

## Inheritance — the highest-applicable-taxon rule

Rules in `references/frequency-and-inheritance.md`. Read it before writing statements.

## Frequency convention

Rules in `references/frequency-and-inheritance.md`. Read it before writing statements.

## Mining descriptions

Procedure and decision rule in `references/mining-descriptions.md`. Read it after the printed key is encoded and before generating the file.

## Generating the file

UUIDs need to be fresh for `identifier`, every taxon, every character, every state, and every statement. The pragmatic implementation:

1. Write a one-off Python script in a scratch folder (the system temp directory, or `work/` next to the source) so it doesn't litter the working directory.
2. The script defines:
   - the taxa tree (a list of dicts with nested `children`),
   - the characters (a list of `(key, title, [states])` tuples),
   - a sparse assignment map: `{taxon_or_genus_key: {character_key: state_key OR [state_keys]}}`, where every assignment also records the claim ids it rests on (emit `provenance.jsonl` from these when writing the statements; a hoisted assignment carries the claims of every leaf it covers), capturing which level the trait is set at, with a list when paired uncertain frequencies are needed.
3. Walk the tree. For each `(taxon, character)` where the taxon (or one of its ancestors) sets a state for that character, emit one statement per state of that character — frequencies depend on the assignment shape:
   - **Confident** (assignment is a single state): one statement at `frequency: 1` for that state, all other states at `frequency: 0`.
   - **Uncertain** (assignment is a list of two or more states): one statement at `frequency: 0.5` for each listed state, all other states at `frequency: 0`.
   - Statements only emit at the level where the assignment is set (the ancestor or leaf that defines the state). Descendants without their own assignment for this character inherit at lookup time and need no statements written for them.
4. Validate inside the script: every assignment must reference a state that exists in that character's state list. Fail loudly if not.
5. Resolve UUIDs via `uuid.uuid4().hex`.
6. Carry over `externalServices`, `license` from the example.
7. Set `language`, `title`, `geography.name`, `lastModified` from the user's inputs.
8. Write the JSON, `provenance.jsonl` and `skipped.jsonl`; run `python -m json.tool` on the JSON, and keep the script.
9. Run `tools/verify.py` and `harvest-claims/scripts/claims_vs_key.py KEY.json --provenance provenance.jsonl --skipped skipped.jsonl`. Fix every finding in the generator and rerun both until the verifier passes and the claims audit reports 0 unsupported statements and 0 unaccounted claims. A claim you decide not to encode is not a finding to ignore; it goes on the skipped list with its reason.

Keep the script readable rather than clever — the user may want to inspect or rerun it.

## Companion decisions document

Required contents and format in `references/decisions-document.md`. Read it when writing the companion.

## Hand-off to audit-clavis-key

After writing the JSON, the decisions doc, and the character-audit table, the digitize phase is complete. **Always invoke the `audit-clavis-key` skill next**, passing it the JSON path, the source path, the decisions doc, and the character-audit table. The audit phase enters fresh and runs:

1. Deterministic `tools/verify.py` (repository root) checks (frequency-rule shapes, ID integrity, leaf-vector discriminability).
2. Predicate-disjointness audit on every sibling-state pair.
3. Quantitative-character anchor audit.
4. Source-coverage spot check on a sample of leaf taxa.
5. Apply fixes if violations are found, then re-run.

Do not consider the digitization complete until the audit signs off, which includes the claims audit at zero findings.
