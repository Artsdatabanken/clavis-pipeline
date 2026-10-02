# Status after the TODO pass of 2 October 2026

The pipeline was rewritten after the first full run from this folder (rodent key, 1 October 2026) and the review of its result. Backup of the previous state: `../clavis-pipeline-backup-2026-10-02.tar.gz` and the first git commit in this repository. Nothing below has been exercised in a full run yet; that run is the first open item.

## Done in this pass

**Numbers, frequencies, determinability (decisions 30–32)**
- Measurements are numerical characters everywhere: digitize Protocol 2 rewritten; `score_claims.py` writes `[min, max]` as the union of a taxon's claims; `verify.py`, `check_bins.py`, `claims_vs_key.py`, `coverage_test.py` check ranges; `union_keys.py` carries them; `reconcile.py` unions ranges across sources; `roundtrip.py` counts containment; `redundancy.py` separates on non-overlap; `apply_coarsen.py` and `coarsen.py` never touch them.
- Frequencies from one table (`harvest-claims/references/frequency-table.json`), no voting: `reconcile.py` keeps every asserted value with the highest frequency any source gives; rounding noise flagged and cleaned.
- New skill `determinability-pass` with agent `clavis-usability` and `flag_undeterminable.py` (comparatives, bundles, relative words, shades, bins-as-states); runs on the merged key before the gate; the merge coarsens only through it.

**Cut double work (items 1–7)**
- Digitizer works from claims, never rereads the book; flat taxon list; no mining or vision sections (moved to harvest).
- Audit Phase 4 removed; geography lives in gate 6 only; Test B is `coverage_test.py`.
- Couplets decomposed once, per taxon along its path (refine Phase 0); merge does not decompose.
- Figures: `find_figures.py` (Surya layout, pdfimages, captions, sparse pages) with crops; `ocr_pdf.py --layout`.

**More deterministic steps (items 8–17)**
- `score_claims.py` (statements from claims with provenance), `find_sections.py` (taxon pages, section, printed-page offset, per-taxon text files), `taxon_names.py` (vernaculars from the adapter), number and qualifier parsing and dedup in `check_claims.py`, `concordance_candidates.py`, `cleanup_location.py` (measured), `run_gates.py` (eight gates, one table, one exit code). Bin cut points are obsolete (numerical characters). Decisions documents are assembled from the scripts' tables.

**Found by the run (items 19–25)**
- `roundtrip.py` rewritten on `spec.json` with chained renames and non-exclusive strictness; reproduces the run's strict result (1815 / 304 / 167 / 0) exactly.
- `reconcile.py` rewritten on `spec.json` (per-source maps, non-exclusive, numerical).
- `verify.py` reads the character type; non-exclusive characters no longer warn.
- Scratch directory per agent required in every brief; `md_to_pdf.py` optional everywhere.
- Characters only one species is described with: valid when the other species are known to lack the trait (then it is one character with several states); useless and removed by the merge only when the other species are unknown. Written into digitize and merge. Decided 2026-10-02.

**Token cost (items 34–37)**
- Per-taxon files and figure crops instead of sections and pages; claims instead of books; briefs with an invariant prefix; `tools/token_report.py` as gate 8. Model pinned (`model: opus` in agents, forced in `.claude/settings.json`).

**Guides and docs**: workflow document rewritten (sections 5–13), README, AGENTS.md, skill texts, claim schema, Claude guide.

## Open

1. **First full run on the rewritten pipeline**, same six rodent sources and list, then compare with `Agentic/Gnagere-run2/leveranse/gnagere.rodentia.json` (separability per pair, characters, claims coverage, cost). Expect rough edges in the new scripts on real data; fix them in the scripts, not in prose.
2. **Viewer and editor**: numerical characters (range input, comparison against `[min, max]`, optional tolerance), implied zeros on exclusive characters, and short ids. The format side is Wouter's.
3. Model comparison: Sonnet 5.5 on the same job (`.claude/settings.json` and the four agent files), then other models through OpenRouter; record in `guides/`.
4. Decide whether the final gate gets its own fresh agent instead of the orchestrator (the gates are scripts, so this is about who fixes).
5. `skills-ref validate` on the skills (needs `pip install skills-ref`); repo URL placeholder in README and guides.
6. Cheaper model for harvesting (Haiku halves cache-read price); measure quality first.
7. `translate-json`: untouched in this pass; its vernacular adapter still lives inside the skill.
