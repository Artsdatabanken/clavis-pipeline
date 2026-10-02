---
name: merge-clavis-keys
description: Merges several independently digitized and audited Clavis keys into one key that provably preserves every source's information. Union-first (equal weight per source), one spec file for the character concordance and per-source state maps, intersection-first reconciliation with every asserted value kept on real disagreement, numerical characters merged as the union of ranges, hierarchy from a taxonomy-register adapter, measured coarsening and location cleanup, and a zero-loss round-trip against every source. Use when the user asks to combine, merge, or collate multiple Clavis keys covering the same taxa. Requires the source keys to be audited first.
license: MIT
compatibility: Python 3.11+ and network access to a taxonomy register through adapters/taxonomy/.
metadata:
  author: Artsdatabanken
  version: "2.0"
  pipeline: clavis-pipeline
---

# Merge several Clavis keys into one

**Never delete or overwrite the user's files.** Write new files; leave the originals in place.

Combines N audited keys covering roughly the same taxa into one key that keeps every source's information, and proves it. Built on a six-source merge of the Norwegian rodents (not included here).

## Inputs

- The source keys, **audited** (`audit-clavis-key`); unaudited drafts propagate their defects.
- The species list CSV.
- Target language.

## Principles

- **Equal weight per source**, structurally: the union of everything first (a union has no order), then reduce. Never pairwise or sequential merging.
- **Preserve, don't average.** A precise source narrows a vague one (intersection); a real disagreement keeps every asserted value reachable. Numbers are the union of ranges. Frequencies are weak priors, never vote shares. The round-trip at the end proves nothing was lost, claim by claim.
- **Scripts decide what can be measured**: whether a location character is needed, whether a coarsening is affordable, which rank to keep. The agent decides meaning: which source characters are the same observable, how labels map.

## Pipeline

Work in `merge/` with numbered intermediates so any phase can be redone.

### 1. Trim and resolve names

Resolve every scientific name through the taxonomy adapter (`adapters/taxonomy/`, NorTaxa by default). Synonyms get an **alias table with evidence** (`alias.json`: `{"Source name": ["Accepted name", "evidence"]}`). Never accept string-similarity suggestions; an unresolvable name is a question for the user.

### 2. Union

`scripts/union_keys.py --csv species.csv --alias alias.json --out 03-union.json KEY1.json KEY2.json ...`: trims to the list, namespaces ids, tags every character with its source ("Trait [src]"), merges taxa by accepted name. Numerical characters and their ranges pass through unchanged. One file per source, exactly once.

### 3. Couplets

A source whose characters are verbatim couplets (multi-clause states bundling several traits) was decomposed by `refine-clavis-key` before it was audited. Do not decompose again here; if a source arrives undecomposed, send it back through refine and audit first.

### 4. Concordance and state maps: spec.json

`scripts/concordance_candidates.py 03-union.json --out candidates.md [--glossary glossary.json]` lists pairs of source characters that probably describe the same observable (title similarity, glossary, shared labels, overlapping ranges, data agreement as evidence). Decide by **meaning** (what does the user look at?) and write `spec.json`, format in `scripts/reconcile.py`: per canonical character its type, unit (numerical), ordered states (categorical), and for every source character that feeds it a map from each source label to one or more canonical labels, `[]` for "says nothing". Maps are per source character, because "ja" means different things in different characters. A source character may feed several canonical axes.

Measurements: every source's measurement character is numerical (the audit guaranteed it), so the member map is `{}` and `reconcile.py` unions the ranges. A source in another unit gets `{"scale": f}` (cm into mm: 10). A source whose numbers are key thresholds ("shorter than 30 cm", the open end closed at a chosen limit) gets `{"bound": true}`: its ranges that touch the source character's min or max give way to the measured ranges they overlap and stand only where nothing was measured or they disagree; the round-trip counts them as narrowed. A source that still has bins must be converted to ranges in its own key first (each bin becomes `[lo, hi]` with open ends closed at the character's min/max).

### 5. Reconcile

`scripts/reconcile.py 03-union.json spec.json 04-reconciled.json --lang nb`

- Exclusive: a source feeding an axis through several of its characters is intersected first (one vote per source); then intersection across sources; empty intersection = real disagreement, every asserted value kept. The most likely value is 1, the others keep their prior. Read `04-reconciled-conflicts.json` as a **mapping-error detector first**: four sources against one is usually a wrong map, not a disagreement.
- Non-exclusive: union of asserted states, frequency the highest any source gives.
- Numerical: union of ranges per taxon; the character's min/max from the data.

### 6. Cleanup (measured)

- `scripts/cleanup_location.py 04-reconciled.json 05-cleaned.json --match "^(Utbredelse|Forekomst|Occur|Distribution)" --removed 05-removed.json`: a location character stays only for the species whose pairs need it (last route, or a drop below 3 routes); stripped elsewhere; dropped when no pair needs it. All logged in `removed.json` in the round-trip's format.
- Species statistics no user can answer on an encounter (abundance, gestation, litters per year): the digitizers skipped them; if any survived, remove and list them in `removed.json` with a reason.

### 7. Hierarchy

`scripts/choose_hierarchy.py species.csv` decides the rank from the data (≤ 16 species: flat; else the deepest rank that is complete and groups into 2 to n/2 groups). `scripts/build_hierarchy.py 05-cleaned.json 07-hierarchy.json --root <Taxon> --rank <rank> --cache species.csv.taxonomy-cache.json` builds the tree from the register and hoists every group all leaves under a node share, whole frequency vectors together; it aborts unless every leaf's effective values are unchanged. `scripts/vernacular.py KEY.json --lang nb` fetches vernacular names from the adapter; missing ones stay empty.

### 8. Determinability pass

Hand `07-hierarchy.json` to `determinability-pass` (a fresh agent inside `build-clavis-key`). It returns the key with shades merged, comparatives rewritten or removed, bundles split, each change logged as a rename file for the round-trip.

### 9. Coarsening (measured)

`scripts/coarsen.py IN.json 08-coarsened.json --neighbours neighbours.json --workdir coarsen/ --log coarsen-log.json`: candidate merges of neighbouring categorical states (the determinability pass writes `neighbours.json`), each accepted only when no pair loses its last route, no pair with ≥ 3 routes drops below 3, and the character keeps ≥ 75 % of its power, both per step and cumulatively. Exclusive characters only; non-exclusive and numerical are never coarsened. Each step is a rename file.

### 10. Finalize

`scripts/finalize.py 08-coarsened.json KEY.json --removed 08-zero-power.json --order order.json`: drops characters no answer can ever rule a species out with (one species scored, every other species unknown; a trait that other species are scored as lacking stays, because it separates), lists them in the removed file, orders states (numeric ascending, months), orders characters by field-answerability tiers you write in `order.json`. Then metadata (title, geography = the list's region, licence as a full URL, `lastModified`).

## Verification

`build-clavis-key/scripts/run_gates.py KEY.json --csv species.csv --sources work --out leveranse --spec spec.json --alias alias.json --removed removed.json --rename coarsen/step-01.json ... --source-keys src/*.json`: verifier, bins and ranges, per-source claims audits, round-trip (`scripts/roundtrip.py`, reads spec.json and the rename chain; zero LOST), redundancy, geography, coverage, tokens. Re-run after every change; a stale rename chain is the classic false loss.

## Deliverables

The key plus `gates.md`, `decisions.md` (conflicts resolved, maps, removals, hierarchy choice, coarsening steps, with reasons), `roundtrip-report.md`, `redundancy-report.md`, `removed-characters.md`, `coverage.md`, `tokens.md`. Key language throughout; Markdown, PDF only when the converter's dependencies exist.
