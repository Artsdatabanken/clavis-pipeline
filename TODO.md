# After the first run from this folder (rodent key, Gnagere-run2, started 2026-10-01)

Changes agreed during the run, to apply once it has finished and been compared with the August key. Nothing here is applied yet.

## Cut double work

1. **Digitizer reads from claims, not from the book.** Remove "read every page", "vision-read figure labels" and "mining descriptions" from `digitize-clavis-key`; the harvester did that. The digitizer opens a page only when a claim is ambiguous. Biggest token cut in the run.
2. **Audit Phase 4 (source-coverage spot check) is superseded** by the claims audit, which is exhaustive. Drop it; keep its geography sub-check in one place only (the verifier's `--without` or the merge gate, not both plus Phase 4).
3. **Partition Test B (coverage of asserted values) as a script.** The asserted values are the `value` fields of the claims per character. Diff them against the states deterministically; the model only judges overlaps (Test A). Currently done in prose twice (digitizer Protocol 1, auditor Phase 2).
4. **No per-source taxa trees.** Digitizers emit a flat species list; the merge builds the hierarchy from the register anyway and redoes the hoisting.
5. **Couplet decomposition once.** If `refine-clavis-key` ran on a transcoded source, the merge must not decompose it again.
6. Housekeeping: the auditor's Phase 1 verifier run on a file the digitizer just passed; three separate register caches in the merge scripts; the species CSV could carry resolved ids.

## Figures from scans

7. **`find_figures.py`**: per source, a `figures.json` of (page, bounding box, caption) so harvesters get figure crops instead of whole pages, and open a full page only when its OCR text is unreadable. Two backends: Surya layout labels for scanned books (already computed in `tools/ocr_pdf.py`, currently discarded after reading-order), `pdfimages -list` for born-digital PDFs. Cross-checks: caption words in the text layer ("Fig.", "Pl.", "Foto"), and pages whose text covers much less area than their neighbours (full-page plates). One sentence in `harvest-claims`: read the listed crops; whole page only when the text is garbled.

## Still open from before the run

- Compare the run's key with `Gnagere/gnagere_merged.json`: statements, characters, separability per pair, what each has that the other lacks.
- Repo URL and "validated on Opus 4.7 through 5.5" in `guides/claude-code.md` are placeholders.
- `git init`, run `skills-ref validate`.
- Model comparison: this run is Opus; repeat on Sonnet 5.5, then other models through OpenRouter, same sources, same list. Record in `guides/`.
- Decide whether the final gate gets its own fresh agent instead of the orchestrator.

## More deterministic steps (ranked by tokens saved)

8. **Scoring from claims**: trait matches character and value equals a state label or falls in a bin -> statement with provenance, by script. Model handles only the residue.
9. **Taxon-to-page index and section bounds** from species-name hits in the text layer (plus register synonyms); model confirms the two edge pages only.
10. **Printed-page offset** parsed from OCR headers/footers.
11. **Numbers and qualifiers in claims**: regex values into numeric ranges with units; qualifier from a per-language word list.
12. **Bin cut points** proposed by optimization over the numeric ranges per taxon; model writes the reason only.
13. **Frequency words to numbers**: one fixed table per language, applied everywhere.
14. **Concordance pre-filter in the merge**: normalized label similarity + bin overlap + synonym glossary -> candidate pairs; model decides candidates only.
15. **Decisions document assembly** from skipped/provenance/bin/merge logs by template; model adds reasoning paragraphs.
16. **`run_gates.py`**: all seven gates, one table, one exit code.
17. **Claim dedup/normalization** across pages before any model step.
18. Cheaper model for harvesting; keep skill text byte-stable so it caches across agent calls.

## Found by the 2026-10-01 rodent run

19. `roundtrip.py` reported 105 losses the merge agent judged false and replaced with its own checker (Gnagere-run2/work/merge). Diff the two; fix the stock script so gate 4 runs on ours.
20. `apply_coarsen.py` turns non-exclusive (multi-choice) values into shares (five habitats -> 0.2 each). Must leave non-exclusive characters at 1.
21. `verify.py` warns FREQ-MULTI-ONE/FREQ-MIXED on non-exclusive characters; make it read the character type.
22. Artfakta couplet decomposition (refine) combined couplets too loosely, widening measurement ranges; the fix was to follow each taxon's own path through the key. Encode that in refine-clavis-key.
23. Harvester agents shared one scratchpad and overwrote each other's scripts; give every agent its own scratch dir in the brief (the digitize brief already says so).
24. Decide: keep or drop the 43 single-species characters the merge removes (removed-characters.md). A ranking interface could use them.
25. `md_to_pdf.py` dependencies absent in the agent environment; either make PDF optional in the skills or ensure requirements are installed before a run.
26. **Coarsening too weak for colour-type characters**: M. agrestis back colour has six shades (rød 0.04 ... gråbrun 0.5) from "mørk gråbrun / mer rustbrun / mørk til rødbrun". Merge adjacent shades until each state is field-answerable; August had three states.
27. **Vote shares presented as frequencies**: equal-weight source voting yields 0.375/0.625 for a hind-foot bin where the sources agree in substance ("oftest over 24", "opptil 2,5 cm", "< 30 mm"). Only spread frequency when sources genuinely disagree; otherwise use the most precise source.
28. **Overstated mappings**: Micromys ears "stikker tydelig fram 1.0" from quotes saying "små runde ører". Scoring must not assert more certainty than the quote; check in audit Phase 2 against the claim text.
29. Rounding: 0.9999 should be 1.

## Decided 2026-10-01 after the spot check

30. **Numbers are numerical characters, always.** Measurements go into the key as Clavis numerical characters with `[min, max]` per taxon; no bins, no cut points, no voting. Merged range per taxon = union across sources (lowest min, highest max). The format supports this already; the pipeline (digitize, merge scripts, verify, coarsening) must produce and carry it, and the editor and the viewer must handle numerical characters properly rather than the pipeline working around them. The interface side is Wouter's (format, editor, viewer are his).
    Everything that touches numbers follows:
    - `harvest-claims`: parse numeric values and units from claims (item 11) so a measurement is a number from the start.
    - `digitize-clavis-key`: Protocol 2 ("anchors", bins with cut points) is replaced by "every measurable trait is a numerical character with unit and `[min, max]` per taxon"; no binned states for measurements. Label conventions: one unit per character.
    - `audit-clavis-key` Phase 3: checks that no measurable trait was encoded as categorical bins, that every numerical statement is `[min, max]` with min <= max inside the character's range, units consistent, and that each range matches the claim it cites. Phase 2 partition tests do not apply to numerical characters.
    - `tools/verify.py`: already validates `[lo, hi]` inside the character range; add unit presence and min <= max on the character itself. `check_bins.py` becomes a range check (overlap between taxa is fine; gaps are not a defect).
    - `claims_vs_key.py`: a numerical statement is supported when its range covers the cited claim's number or range.
    - `merge-clavis-keys`: concordance by unit and trait, union of ranges per taxon, no coarsening of numerical characters; `roundtrip.py` counts a numeric claim as survived when the merged range contains it.
    - Redundancy report: two taxa are separated by a numerical character when their ranges do not overlap; partially overlapping ranges count as a partial route, reported separately.
    - Determinability pass (item 32): numerical characters pass by construction; a measurement needs no comparison specimen.
    - Documentation: `docs/clavis-agentic-workflow.md` section "Binning measurements" rewritten; README feature row for numerical values; `references/claim-schema.md` gains `value_num: [min, max]` and `unit`.
    - Viewer and editor: numerical input (a number or a range) and comparison against `[min, max]`; a value inside the range keeps the taxon, outside excludes it (or down-weights, if a tolerance is chosen). Editor: entering ranges per taxon with a unit.

31. **Frequencies are weak priors, not data.** Non-zero when the source admits the value, zero when it excludes it; one fixed word-to-number table per language; no voting, no prose about the exact value. Replaces item 13.
32. **New step and agent: determinability pass.** After merge, before the gate. Sees only the key. For every state: can one person, with one specimen and the guide, no comparison specimen and no experience, pick it? Merge shades to a small palette, rewrite comparatives ("darker than X", "larger") into absolute terms or drop them, split remaining bundles. Script flags candidates (comparative words, shade count per character, "or"); the agent judges only those; changes applied through refine-clavis-key scripts; the gate then proves no pair lost its last route. Same criterion stated in digitize so less reaches the pass.
33. Done 2026-10-02: a nested agent with no model in its definition or spawn falls back to the main conversation's model (Fable). Fixed with `model: opus` in all agent files, `.claude/settings.json` forcing the sub-agent model, and the build skill requiring `model` on every spawn.

## Token cost (from the 2026-10-01 report: 98% is input; output is 2%)

34. **Fewer calls per agent**: batch reads and script runs; no polling; lower effort for harvest and audit phase 1. Each call re-reads ~136k tokens.
35. **Smaller context per agent**: per-taxon text file for harvesters (not the whole section); digitizer works from claims, opens a page only on demand.
36. **Shared cache prefix**: invariant text first (AGENTS.md, skill, schema), per-agent brief last, nothing volatile in between, so the cache write (USD 64 for 25 agents) happens once per run.
37. Cheaper model for harvesting (Haiku halves cache-read price; Sonnet does not). Measure quality first.
