# Measurements: numerical characters

Part of the `audit-clavis-key` skill. Read when SKILL.md points here.

A trait the source gives numbers for is a `numerical` character with `unit`, `min`, `max`, `stepSize`, and one statement per taxon whose `value` is `[min, max]`. Check, for the whole key:

1. **No measurement as bins.** A categorical character whose states read "under 40 mm / over 40–60 mm / over 60 mm", or "small / medium / large" for a trait the claims give numbers for, is a defect: convert it to numerical in `design.json` and re-score. `flag_undeterminable.py` reports the first kind as NUMERIC-AS-STATES.
2. **One unit per quantity** across the key (all lengths in mm, all ratios in %). Two characters for the same quantity in different units are one character.
3. **Ranges cover their claims.** `claims_vs_key.py` and `coverage_test.py` report a statement whose range does not contain a cited claim's number; the fix is the union of the claims, never a narrower "typical" value.
4. **Open bounds closed sensibly.** "over 24 mm" became `[24, max]`; `max` must be the character's maximum over all taxa, not an invented ceiling. Check `min`/`max` on the character against the data.
5. **Words-only quantities.** A trait the source only describes as "small" or "long" is categorical, flagged as RELATIVE, and kept only when nothing else separates the taxa; otherwise its claims are skipped with `comparative-unresolved`.
6. **Counts.** Few distinct integer values with no ranges in the source may stay categorical (one state per integer). Any range makes the character numerical.

Required output: in the character-audit table, every numerical character with its unit and the span of its ranges; every converted character listed in the findings.
