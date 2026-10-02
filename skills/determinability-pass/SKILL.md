---
name: determinability-pass
description: Makes every state of a Clavis key answerable by one person with one specimen and the guide, without a comparison specimen or prior experience. A script flags comparatives, bundles, relative words and over-fine palettes; the agent decides only the flagged rows, merges shades, rewrites comparatives in absolute terms or drops them, converts leftover bins to numerical characters, and the gate afterwards proves no species pair lost its last route. Runs on the merged key before the final gate, and on request on any key. Use when a key reads like a transcription instead of a field key.
license: MIT
compatibility: Python 3.11+. No network. Sees only the key, never the sources.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Determinability pass

**Never delete or overwrite the user's files.** Output is a new key file plus a rename file per change.

One criterion, applied to every state: **can one person, with one specimen (or one find, one track) and this guide, no comparison specimen and no experience, pick it?** Precision on paper that a user cannot act on is not information; it is a question they cannot answer. This pass sees only the key. It does not reread sources; what the sources said has already been preserved and is proven by the round-trip.

## Procedure

1. `scripts/flag_undeterminable.py KEY.json --out flags.md --claims claims.jsonl --provenance provenance.jsonl` lists, per character and state: COMPARATIVE (a supporting claim was marked comparative by the harvester), BUNDLE (a supporting claim lists several values), RELATIVE (the source gives numbers for this trait elsewhere, this state has none), SHADES (an exclusive character with more than six states), NUMERIC-AS-STATES (labels that start with numbers). The flags come from the claims and the key's structure, not from words of any language. On a merged key, pass the union of the sources' claims and provenance files; without them only SHADES and NUMERIC-AS-STATES are checked.
2. Decide every flagged row, nothing else:
   - **SHADES**: group the states into a palette a user can name on sight (for colour: rarely more than four or five). Write the merges into `neighbours.json` for `merge-clavis-keys/scripts/coarsen.py`, which accepts each merge only if no species pair loses its last separating route and no pair with three or more routes drops below three; a merge the script refuses stays unmerged, and you note why the fine distinction was the only separator.
   - **COMPARATIVE**: rewrite in absolute terms when the key carries the numbers or a plain description ("darker than the field vole" with a grey-brown state becomes that state); otherwise drop the state or character and log it in `removed.json` with reason `not determinable`.
   - **BUNDLE**: split into one state per value with `refine-clavis-key/scripts/apply_state_splits.py`; the taxon gets a statement on each.
   - **RELATIVE**: keep only when nothing else separates the taxa it separates (check `redundancy.py`); otherwise drop and log.
   - **NUMERIC-AS-STATES**: convert to a numerical character: each bin becomes `[lo, hi]`, open ends closed at the character's extremes; one statement per taxon as the union of its bins.
3. Every relabel or merge is written as a rename file in `<merge folder>/determinability/` (`{"Character": {"old": "new"}}`, `__characters__` for titles) so `roundtrip.py` can chain it; every removal goes to `removed.json`.
4. Run `tools/verify.py` and `merge-clavis-keys/scripts/redundancy.py` on the result and report: flags before and after, pairs separated before and after (must not drop), what was merged, rewritten, converted, removed.

## Output

`<key>.determinable.json`, `neighbours.json`, rename files, `removed.json` additions, and `determinability-report.md` with the numbers and the list of decisions in the key's language.
