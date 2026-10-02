# Protocols: atomic states and measurements

Part of the `digitize-clavis-key` skill. Read when SKILL.md points here.

### Protocol 1: Atomic states — partition both ways

The states of a categorical character are the menu the user picks from. They must form a **partition** of every value the source asserts for that trait: each asserted value falls into exactly one state, never two, never none. Test both directions for every character, against the claims, and record the result in the character-audit table before scoring.

**Test A, no overlap.** For every pair of sibling states: is there a value that satisfies both?

- Range/superset: "Six" next to "Eight or fewer" (six fits both). Re-cut: "Six", "Seven to eight", "Nine or more". With numbers involved, the character is numerical and this test does not apply.
- Bundled distinguishables: "Brown" next to "Brown or grey". Split the bundle; a taxon the source calls variable gets a statement on each state.
- Cross-axis: "green" next to "with two prominent spots". A specimen can be both. Split the character into colour and pattern.

**Test B, no gap.** For every claim value feeding the character: does some state cover it? "5 or fewer" includes 4, 3, 2, 1, 0; if the states are Four, Five, Eight, Ten, a user counting three has no answer. Add the state or widen one. `audit-clavis-key/scripts/coverage_test.py` runs this test from the provenance; the digitizer runs it by reading the trait table.

Both tests use only what the source asserts, read with ordinary language and arithmetic. Biological knowledge about what is "realistic" never shrinks the value space; that is how gaps get papered over.

**Required artifact.** The character-audit table, one row per character:

| Character | Type | States | Test A (overlap) | Test B (gap) | Fix applied |
|---|---|---|---|---|---|

### Protocol 2: Measurements are numerical characters

A trait is a **measurement** when the source gives numbers for it: length, mass, count on a scale, ratio, duration, angle, temperature, depth, age. A measurement is always a `numerical` character:

- `unit` set once per character; one unit per quantity across the key (all lengths in mm, ratios in %).
- Each taxon gets one statement with `value: [min, max]`, the union of the source's numbers for it. An open bound ("over 24 mm", "opptil 2,5 cm") closes at the character's `min` or `max`, which the design sets or the script takes from the data.
- No bins, no cut points, no "under X / over X–Y" states, no paired frequencies across a boundary. The viewer compares the user's measurement with the ranges.
- A quantity the source only describes in words ("small", "long") is not numerical. It becomes a categorical character with those words as states, and the determinability pass flags it as relative. Keep it only if it separates taxa nothing else separates; otherwise skip the claims with `comparative-unresolved`.
- Counts of enumerable things with few distinct values ("5 or 6 toes") may stay categorical with one state per integer when the source never gives ranges; the moment a range appears, the character is numerical.

**Required artifact.** The same character-audit table marks every numerical character with its unit and the span of its ranges.
