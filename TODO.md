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

## Run 3 (2 October 2026, rewritten pipeline, Opus 5.5)

All required gates passed. 86 characters (24 numerical), 873 statements, 259 KB (run 2: 84 bins, 2774 statements, 737 KB). But fewer separations (274 of 276 pairs; median 6 routes; run 2: 275, median 8) and higher cost (USD 173, 124 agent transcripts; run 2: USD 119, 25). Causes found and fixed in `Agentic/Gnagere-run3/leveranse/` and the commits after it:
- 85 characters removed because only one species was scored and the rest were unknown. New rules (2 October): a trait the source presents as diagnostic is scored absent for the other species it describes; a species the source says cannot be told from another gets that one's values. Both by `score_claims.py` from marked claims (`diagnostic`, `same_as`); the *M. agrestis* / *M. levis* separation of run 2 came from exactly such a statement in Bjärvall.
- 108 harvester agents (one per species per book): now one per source, species by species.
- Thirteen script fixes found on real data (units, exact matching, open ranges, numerical support in merge scripts, page override, cost gate), committed.

## Added 2 October, for smaller models

- `draft_design.py`: design.json drafted from the claims; the digitizer edits (merges, names, absent states) instead of writing.
- `draft_spec.py`: spec.json drafted from the union with identical titles and labels already placed; the merge agent decides only the characters left alone and the labels left null.
- `plan.py`: the orchestrator's bookkeeping: detects the phase from the files, prints the commands, writes every agent brief with paths filled in.
- Skills: checklists in the first lines, third-person descriptions, all under 110 lines (the limit is 500; a partial read of the first 100 lines gets the whole procedure).

## Open

1. **Run 4**: same sources and list, to measure the effect of the two scoring rules and per-source harvesting on separability and cost. Compare with run 2 and run 3.
2. **Viewer and editor**: numerical characters (range input, comparison against `[min, max]`, optional tolerance), implied zeros on exclusive characters, and short ids. The format side is Wouter's.
3. Model comparison: Sonnet 5.5 on the same job (`.claude/settings.json` and the four agent files), then other models through OpenRouter; record in `guides/`.
4. Decide whether the final gate gets its own fresh agent instead of the orchestrator (the gates are scripts, so this is about who fixes).
5. `skills-ref validate` on the skills (needs `pip install skills-ref`); repo URL placeholder in README and guides.
6. Cheaper model for harvesting (Haiku halves cache-read price); measure quality first.
7. `translate-json`: untouched in this pass; its vernacular adapter still lives inside the skill.

## Run 4 (2 October 2026, Sonnet throughout)

All required gates passed. 74 characters (18 numerical), 869 statements, 253 KB; 273 of 276 pairs separated, median 7 routes; 85 minutes; USD 36 for everything including the orchestrator (run 3: USD 173). Found broken: find_sections.py wrong per-taxon pages on most books (harvesters fell back to the whole section); find_figures.py 50 minutes on scans and no usable crops without Surya layout; draft_spec.py collides same-title different-unit characters; hoist_statements.py and apply_coarsen.py crashed on numerical values (coarsen patched); plan.py omits --alias; containment matching in score_claims.py put some wrong statements that the audits caught; the orchestrator removed the M. levis look-alike copy over a name confusion. Next: fix these, then run 5 on Sonnet.

## Run 5 (2 October 2026, Opus orchestrator, Sonnet agents)

All required gates pass, including the new check of claims against the books (every quote verbatim, every unquoted stretch decided). 81 characters (21 numerical), 934 statements; 275 of 276 pairs separated, only the two beavers inseparable (no source separates them); 73 min; USD 56 (USD 18 orchestrator). Default from now: Opus orchestrator, Sonnet agents. To check: M. arvalis / M. levis are separated only by one sign character although Bjärvall says they cannot be told apart externally (likely one source describing levis signs differently from another source for arvalis); the shade merge of "rødbrun" with "mørkebrun til svart" accepted by the coarsening script; open bounds closed at agent-chosen limits (listed in decisions.md); ears and eyes "store/små" not flagged because the flag script needs the claims to say comparative.
