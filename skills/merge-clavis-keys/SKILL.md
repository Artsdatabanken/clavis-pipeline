---
name: merge-clavis-keys
description: Merge several independently digitized and audited Clavis keys into one key that provably preserves every source's information. Union-first architecture (equal weight per source), deterministic taxonomy via a taxonomy-register adapter (NorTaxa by default), intersection-first conflict policy with source-weighted frequencies on real disagreement, redundancy-based state coarsening, and a zero-loss round-trip verification against every source. Use when the user asks to combine, merge, or collate multiple Clavis keys covering the same taxa. Requires the source keys to be audited first.
license: MIT
compatibility: Python 3.11+ and network access to a taxonomy register through adapters/taxonomy/.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Merge several Clavis keys into one

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant.

Combines N independently digitized and audited Clavis keys covering (roughly) the same taxa into one key that preserves every source's information. Built from a six-source merge of the Norwegian rodents; that project's decisions document is the worked example for every rule here (not included in this repository).

## Inputs

- The source keys — **audited** (`audit-clavis-key`) first; merging unaudited drafts propagates their defects into everything downstream.
- The species list CSV (scope of the merged key).
- Target language (all titles, states and companion docs in one language).
- Hierarchy depth (see Phase: hierarchy) — ask the user if not specified.

## Principles

- **Equal weight per source.** Achieved structurally, not by vote-tallying: build the *union* of everything first (a union has no order), then reduce. Never merge pairwise/sequentially — the last key merged would count more than the first.
- **Preserve, don't average.** A precise source beats a vague one (intersection); a real disagreement keeps every asserted value reachable. Information is only ever narrowed or kept, never silently dropped — the round-trip check at the end proves it claim by claim.
- **Too much work for a human is the point.** Collate everything; don't sample.

## Pipeline

Work in a `merge/` subdirectory with numbered intermediates so any phase can be redone. Each phase gets a short report.

### 1. Trim and resolve names

Trim each source key to the species CSV. Resolve every scientific name through the taxonomy adapter (`adapters/taxonomy/`; NorTaxa by default, select another with `CLAVIS_TAXONOMY` or `--taxonomy`), which returns the accepted name's id and full higher classification. The scripts cache responses next to the CSV.

- Synonyms get an **alias table with evidence** (the source's own synonymy, or a documented genus transfer) mapping source name → accepted name.
- **Never auto-accept string-similarity suggestions** (`/Suggest` and its kin are string matching, not taxonomy — they will happily map one species onto a *different* species: *Microtus subarvalis* → *M. arvalis* nearly merged two species). An unresolvable name is a question for the user, not a guess.
- Dead-character rule after trimming: drop a character only if **all** leaves are answered *and* identical. A character answered for only a few taxa can still be diagnostic (a notch on one species' incisors identifies it); "all answered taxa agree" is NOT sufficient grounds to drop.

### 2. Union

Namespace every source's ids, concatenate taxa/characters/statements into one file. Tag each character internally with its source (stripped again before shipping — titles the user sees never carry provenance).

### 3. Merge taxa

Same accepted name = same species. Merging taxa is lossless while characters remain source-tagged: each species simply carries all six sources' statements side by side.

### 4. Resolve couplets into atomic axes

Any source that encoded dichotomous couplets verbatim (states that are multi-clause sentences bundling tail + ears + gait) is decomposed into one character per observable axis — exactly as `digitize-clavis-key` would have done, applied late. Do this **before** cross-source character matching; you cannot match a bundle against an axis.

### 5. Merge characters

Build a concordance: which source characters describe the same observable trait. Match by **meaning** first (what does the user look at?).

- Species-by-species agreement of the data is **evidence when meaning is uncertain, never the generator**: with few species, unrelated characters match perfectly by chance (chewing-surface pattern matched nose shape). Use the data test when two characters *may or may not* be the same trait, not blindly.
- Merging characters whose state vocabularies differ is fine — reconciling those is the next phase.
- **Measurement bins are mapped by computed interval overlap, never by hand** — hand-copied bounds are where transcription errors hide. Parse each source label's numeric range and map it onto every canonical bin it overlaps (see the shrew merge's `build_concordance.py` for the worked pattern).

### 6. Reconcile states

For each merged character, map every source label onto one canonical state set (atomic per the digitize protocols):

- **Intersection first**: if the sources' allowed-value sets for a taxon intersect, the intersection is the answer (the precise source narrows the vague one). Count these as "narrowed", not lost.
- **Read the conflict list as a mapping-error detector before accepting it as disagreement.** A "conflict" where four sources say one thing and one source the opposite is far more often a concordance/state-map error than a real disagreement — on the shrew key the tail-keel "conflict" was the mapper having two of Gibson's states inverted; corrected, the sources agreed all along. Only what survives that scrutiny is a real disagreement.
- **Empty intersection = real disagreement**: source-weighted frequencies — each source is one vote, split evenly across the values it allows; frequencies are the normalized sums. Every value any source asserts stays reachable. Majority-rule (dropping minority claims) destroyed 52 source claims on the rodent key before this replaced it.
- **Frequencies on state merges are summed** (states of a character are mutually exclusive: P(A or B) = P(A)+P(B)), never max'd. A group summing over 1 (source admitted three values, two of which merged) is scaled back to sum 1, preserving relative weights.
- **Graded frequencies (0.95/0.05…) are preserved verbatim.** Never round to 0.5. Beware: `refine-clavis-key`'s `apply_character_split.py`, `refine_clavis.py` and `hoist_statements.py` all silently flatten graded frequencies — do not run them on merged data; write hoists that move whole frequency vectors.
- **Numerical measurements**: re-extract raw values from the source texts rather than pooling already-binned states (binning destroyed the precision once). Choose bin cut-points by maximizing species pairs separated. No `numerical` character type for now — not implemented in the tooling; use binned exclusive states.
- **Non-committal groups** (taxon at frequency > 0 on every state) say nothing — flag them; a character non-committal for most taxa is a removal candidate.

### 7. Hierarchy

Taxonomy from the taxonomy service, deterministically — never from the sources (they disagree on circumscription).

- **Depth is decided by the data, not asked** — `scripts/choose_hierarchy.py species.csv`. Grouping exists only to keep the species list scannable, so the first question is whether any grouping is needed at all: **up to 16 species, the flat list under the root is fine and no intermediate rank is used** (7 shrew species directly under Soricidae was judged right; a Sorex node would only have added a level). Above that, a rank qualifies if it is *complete* (every species has an ancestor at that rank) and *groups* (at least 2 and at most n/2 groups); of the qualifying ranks keep **only the deepest**, and collapse any node left with a single child. Rodentia (29 spp): suborder (4) and family (6) qualify, genus (18) does not → **family–species**. Report the choice with its numbers.
- **There is no overriding in Clavis.** A parent's statement binds every descendant; a descendant restating the character makes the key invalid (`verify.py` check `INHERIT-CONFLICT`). Hoist a group to an ancestor only when *every* leaf under it agrees exactly — and remove it from the leaves when you do.
- Flatten with `scripts/flatten_hierarchy.py IN.json OUT.json` (root → root's children → leaves): computes effective values per leaf first, rebuilds, re-hoists what's shared, aborts unless every leaf is bit-for-bit unchanged.
- **Vernacular names**: `scripts/vernacular.py KEY.json --lang nb` fetches them from the taxonomy adapter by the taxonID already in `externalReference` (same source as the taxonomy, so names and placement can't drift). Preferred-status names only; intermediate ranks with no registered name stay empty — never invent names.

### 8. Cleanup

- **Keep a character only if it can be used to identify the animal.** The test: is it something a user can observe on an encounter or a find — the specimen, its tracks, a nest with countable young, a caravan of young walking behind the mother, activity in daylight? Species statistics fail even when they are solid biology: abundance ("how common"), gestation length, weaning age, eye-opening age, litters per year, mating-season boundaries, territorial-vs-nomadic — answering any of them requires long-term study or already knowing the species. Drop failures unless a pair needs them, and book every removal in the round-trip.
- **Location-based characters are a last resort.** "Occurs in Norway", "found in region X", "distribution in Europe" and kin are context-bound — a user outside the assumed region cannot answer them, and inside it they often answer themselves. Keep a location character only for species pairs that *need* it (a pair that would otherwise lose its last separator or fall below 3 routes); strip its statements from every species that doesn't, and when no pair needs it, drop the character entirely and list it as deliberately removed so the round-trip stays accounted for. On the shrew key all five location characters were droppable at a cost of at most one route on the worst pair.
- **Remove** characters with zero separating power, unanswerable-in-practice characters, and true duplicates (Phase 4 of your own couplet-splitting can create them). Document each removal and its redundancy cost.
- **Coarsen over-granular states.** The union inherits the finest vocabulary of every source ("grå" beside "skifergrå"; five browns), which is precise on paper and unanswerable in hand. Criterion — what the *key* can afford, not what the character uses: a merge is accepted when (a) no species pair loses its last separating character, (b) no pair with ≥3 routes drops below 3, (c) the character keeps ≥75 % of its own separating power — without (c) the search hollows questions out to "under/over 300 mm" while redundancy hides it. Candidates are proposed **semantically** (adjacent bins, neighbouring colour terms) and accepted/rejected by measurement: `scripts/redundancy.py KEY.json --merge PLAN.json`. Greedy: apply the merge gaining most confident cells, repeat.
- **Label conventions and character order** per the digitize skill (percent ratios, one unit, digits, bin form, field-answerability order).

## Verification (all gates, in order)

1. `tools/verify.py` (repository root): PASS.
2. `scripts/check_bins.py` (in audit-clavis-key/scripts): no gaps/overlaps.
3. **Round-trip**: replay every source's positive claims against the merged key. Every claim must be *survived* (some asserted value has frequency > 0) or *narrowed* (by a more precise source) or *deliberately removed* (listed). **Zero silent losses.** The checker maintains rename maps (taxon aliases, character concordance, every state rename/coarsening); **every later rename must be chained into it** — a stale checker reports false losses, or worse, silently skips renamed items while appearing to pass. Re-run after every change.
4. **Redundancy report** (`scripts/redundancy.py KEY.json`): pairs separated, routes per pair, inseparable pairs documented as source limits vs merge artefacts. Numbers are worst-case floors (any frequency > 0 counts as possible).
5. **Geographic occurrence must never be the sole discriminator** for any pair.
6. **Two-way coverage** vs the species CSV: what the key misses (and which source could fix it), what the sources cover beyond the list.

## Deliverables

The merged key + companions (decisions, character-audit, coverage, audit-findings, removed-characters, round-trip report), all in the key's language, PDFs generated at the very end (`audit-clavis-key/scripts/md_to_pdf.py`). Every judgment call — conflict resolutions, coarsenings, removals, the hierarchy choice — goes in the decisions doc with its reasoning.
