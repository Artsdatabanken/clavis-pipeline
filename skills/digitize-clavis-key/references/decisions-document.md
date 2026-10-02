# The companion decisions document

Part of the `digitize-clavis-key` skill. Read when SKILL.md points here.

Alongside the key, write `<key>.decisions.md`: the judgment calls that are not recoverable from the JSON. Write it in the source's language, for the domain experts who will dispute it. Markdown; PDF only at the very end of the whole run, and only if `md_to_pdf.py`'s dependencies are installed (otherwise Markdown is the deliverable, say so).

Most of the content is tables the scripts already produced; assemble, do not retype:

- **Source and scope.** What was digitized, section pages, the species list, taxa the source covers beyond it (from the coverage note).
- **Counts.** Taxa, characters (categorical / numerical), statements, claims scored, claims skipped by reason (from `skipped.jsonl`), verifier and claims-audit results.
- **Characters.** The character-audit table from Protocol 1 and 2, with the trait wordings each character absorbed (`traits` and `values` in `design.json`).
- **Skipped claims.** One line each: taxon, page, quote, reason. This shows the omissions were deliberate.
- **Comparatives.** Each comparative claim and what happened to it: rewritten in absolute terms (how), kept as a state (why a user can still answer it), or skipped.
- **Shades and merges.** Which source wordings were folded into one state and why a user could not tell them apart.
- **Source contradictions.** Where the printed key and the description disagree, which was trusted and why.
- **Where a reasonable reader might differ.** The genuine judgment points, briefly.

Nothing about frequencies beyond "from the table", nothing about bins (there are none), nothing about hierarchy (the merge decides it).
