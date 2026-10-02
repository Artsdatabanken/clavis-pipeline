# Instructions for the AI agent running this pipeline

You are in the Clavis pipeline repository. Its job: turn identification material (scanned books, PDFs, spreadsheets, online keys) into Clavis JSON identification keys, with you doing the reading and judgment and the scripts doing the checking. Read `README.md` for the layout and `docs/clavis-agentic-workflow.md` if you want the reasoning behind the design.

## How to run a job

The user will name a taxon and point you at sources: local files, folders, or URLs. Then:

1. Read `skills/build-clavis-key/SKILL.md`. It is the orchestrator and tells you the order: species list, one digitization per source, one audit per draft, merge, verify, and optionally translate.
2. Each step has its own `skills/<step>/SKILL.md`. Read the one for the step you are on, follow it, and run the scripts it names from `skills/<step>/scripts/`. Do not reinvent what a script already does.
3. For a single step ("audit this key", "translate this key to English"), go straight to that skill.
   The run is not done when the key exists. It is done when the gates in `build-clavis-key` Phase 4 pass with numbers: verifier clean, every claim from every source accounted for, zero silent losses in the merge. A failed gate is work, not a result; fix and re-run until it passes. The final report also states what the run cost: total tokens by kind, the price, and the wall-clock time (`tools/token_report.py` under Claude Code).
4. Work in a `work/` folder next to the sources. Never write into the source folder, never overwrite the user's files; new versions get new filenames.
5. When you digitize several sources, each digitization must see only its own source. Independence between drafts is what the merge step relies on. If your harness can spawn sub-agents, use the three roles in `agents/`: harvesters list claims, digitizers encode, auditors check, and no agent checks its own work. Give each one exactly one source. If it cannot, do the sources one after another in fresh sessions or with the other sources closed.

## Environment

- Python 3.11 or newer. `pip install -r requirements.txt` once. The skills write `python3`; on Windows the command is usually `python`. Use whichever exists.
- Paths in the skills are written with `/`. Python handles that on every platform; when you run shell commands, adapt them to the shell you have.
- OCR (`tools/ocr_pdf.py`) needs Surya, which is a separate install. Everything else is plain Python.
- Network is needed for the taxonomy adapter (name resolution, vernacular names) and for online sources. Everything else runs offline.

## Rules that do not bend

- Source material never enters this repository: no PDFs, scans, page images, OCR text, scraped HTML, or draft keys derived from copyrighted works. If the user asks you to commit, check `git status` for these first.
- Frequencies are graded values in [0, 1], never rounded to 0.5. A parent's statement binds every descendant; never restate a character below an ancestor that has it. The verifier enforces both; run it before reporting done.
- Judgment calls are written down in the decisions document alongside the key, in the language of the source, so an expert can dispute them without rerunning anything.

## If you are not Claude Code

This pipeline has been validated with Claude Code only (see `guides/claude-code.md`). It is written to be harness-neutral, but no one has confirmed that yet for your harness. At the end of the run, tell the user this in one sentence, and ask them to contribute what they learned: copy `guides/TEMPLATE.md` to `guides/<your-harness>.md`, fill it in (what worked, what needed changing, cost, time), and open a pull request. If a SKILL.md needed a change to work for you, include that change in the same pull request.
