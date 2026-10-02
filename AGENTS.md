# Instructions for the AI agent running this pipeline

You are in the Clavis pipeline repository. Its job: turn identification material (scanned books, PDFs, spreadsheets, online keys) into Clavis JSON identification keys, with you doing the reading and judgment and the scripts doing everything that can be measured. Read `README.md` for the layout and `docs/clavis-agentic-workflow.md` for the reasoning behind the design.

## How to run a job

The user names a taxon and points you at sources: local files, folders, or URLs. Then:

1. Read `skills/build-clavis-key/SKILL.md`. It is the orchestrator: species list, prepare each source once, harvest claims (one agent per taxon per source), digitize (one agent per source), audit (one fresh agent per draft), merge, determinability pass (one fresh agent), then the gates.
2. Each step has its own `skills/<step>/SKILL.md`. Read the one for the step you are on, follow it, run the scripts it names from `skills/<step>/scripts/`. Do not reinvent what a script already does; if a script is wrong, fix the script and say so in the report.
3. For a single step ("audit this key", "translate this key to English", "did we miss anything in the book"), go straight to that skill.
4. Work in a `work/` folder next to the sources, deliver in `leveranse/` next to it. Never write into the source folder, never overwrite the user's files; new versions get new filenames.
5. Agents are separate on purpose: harvesters list claims, digitizers encode, auditors check, the usability agent makes states answerable, and no agent checks its own work. Each harvester sees one taxon of one source; each digitizer sees one source's claims; nobody sees another source. If your harness cannot spawn agents, do the jobs one after another in fresh sessions.
6. The run is not done when the key exists. It is done when the gates in `build-clavis-key` Phase 4 pass with numbers: verifier clean, every claim from every source accounted for, zero silent losses in the merge, no pair separated only by location. A failed gate is work, not a result; fix and re-run until it passes. The final report states what the run cost: tokens by kind, price, wall-clock (`tools/token_report.py` under Claude Code).

## Environment

- Python 3.11 or newer. `pip install -r requirements.txt` once. The skills write `python3`; on Windows the command is usually `python`.
- poppler (`pdftotext`, `pdfimages`, `pdftoppm`) for PDFs; `pypdf` as fallback for text. OCR of scans needs Surya (separate install).
- Paths in the skills use `/`; adapt shell commands to your shell.
- Network only for the taxonomy adapter (names, hierarchy, vernaculars) and online sources.
- Models: every agent runs on the model the run was started with, never a more expensive one. Under Claude Code, `.claude/settings.json` forces this.

## Rules that do not bend

- Source material never enters this repository: no PDFs, scans, page images, OCR text, scraped HTML, claims files or draft keys derived from copyrighted works. Check `git status` before any commit.
- Measurements are numerical characters with `[min, max]` per taxon, the union of what the sources say. No bins, no voting on numbers.
- Frequencies are weak priors from one table; 0 excludes, anything above 0 keeps the taxon reachable. No vote shares, no arguments about 0.8 versus 0.7.
- Every state must be answerable by one person with one specimen and the guide, without a comparison specimen or experience.
- A parent's statement binds every descendant; never restate a character below an ancestor that has it. Exclusive characters carry no zero-frequency statements; zero is implied.
- Every statement traces to claims; every claim reaches a statement or a skipped list with a reason. Judgment calls go in the decisions document, in the language of the source.

## If you are not Claude Code

This pipeline has been validated with Claude Code only (`guides/claude-code.md`). It is written to be harness-neutral, but nobody has confirmed that for your harness. At the end of the run, tell the user this in one sentence and ask them to contribute what they learned: copy `guides/TEMPLATE.md` to `guides/<your-harness>.md`, fill it in (what worked, what needed changing, cost, time), and open a pull request. If a SKILL.md needed a change to work for you, include it in the same pull request.
