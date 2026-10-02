# TODO

State on 2 October 2026, after five full runs on the Norwegian rodents and three script checks. History of the runs and the model comparison: `guides/claude-code.md`. Backup of the pipeline before the rewrite: `../clavis-pipeline-backup-2026-10-02.tar.gz` and the first commit.

## Decided

- Measurements are numerical characters with `[min, max]` per taxon, the union of the sources; no bins, no voting. Open bounds close at the extreme the data reaches, never at a number an agent chooses.
- Frequencies come from one table (`harvest-claims/references/frequency-table.json`); 0 excludes, anything above 0 keeps the taxon reachable.
- Every state must be answerable by one person with one specimen and the guide. A relative word ("large ears") is a valid answer when nothing better exists; the flag script shows, per flag, how many species pairs only that character separates.
- A character that separates look-alikes but is not always visible stays: without it the user is left with the two species, which is the truth, and learns what to look for.
- Shades are merged only when a person could confuse them on one specimen: every neighbour pair needs a reason and a state has at most two neighbours (`coarsen.py` refuses anything else). A merge that costs no separation is not a reason by itself.
- A trait the source presents as diagnostic for one species is absent in the others it describes; a species the source says cannot be told from another gets that one's values where it has none. Both by script from marked claims.
- A trait one species has and the others are not known to have (no statement either way) is removed at the end; with a known absence it stays.
- No words of any language in the scripts: meaning comes from fields the harvester sets (`qualifier`, `values`, `value_num`, `unit`, `diagnostic`, `same_as`) and from `"location": true` in the merge spec.
- The claims are checked against the books (every quote verbatim, every unquoted stretch decided by the auditor), the key against the claims, the merged key against every source.
- Models: Opus 5.5 orchestrating, Sonnet 5.5 for every agent. Haiku 4.5 tested as harvester and not usable; Fable 5.1 not used (cost). The final gates stay with the orchestrator: they are scripts; a separate agent would only re-run them.
- Script fixes are checked by a Sonnet agent on an existing run's files, not by a new full run; full runs only for changes in the rules that build the key.

## Open

1. **Viewer and editor** (Wouter's side): numerical characters (enter a measurement or a range, compare with `[min, max]`, optional tolerance), implied zeros on exclusive characters, short ids.
2. **Figures from scanned books** need Surya's layout file (`tools/ocr_pdf.py --layout`); without it there are no figure crops. Not yet run on the rodent books.
3. **Species pages**: some species get 15 to 31 pages (family chapters, running headers). Fine for correctness; costs harvesting tokens.
4. **Validator**: `skills-ref validate` needs `pip install skills-ref` (not installed; ask first).
5. **Repository URL** in README and guides is a placeholder until the repository is published.
6. `translate-json` keeps its vernacular-name adapter inside the skill instead of `adapters/`; no functional problem.
7. Reports from other harnesses and models, especially smaller and local ones (`guides/TEMPLATE.md`).
