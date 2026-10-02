# Claude Code

The harness the pipeline was built and validated on. Other harnesses and models: see `README.md` in this folder, and please send your results.

## Setup

Clone the repository and start Claude Code in it: `.claude/skills` and `.claude/agents` already point at the skills and agents, so nothing else is needed. The steps below are only for making the skills available from any folder. Linux and macOS:

```
git clone https://github.com/Artsdatabanken/clavis-pipeline
cd clavis-pipeline
pip install -r requirements.txt
for s in skills/*; do ln -s "$PWD/$s" ~/.claude/skills/; done
for a in agents/*; do ln -s "$PWD/$a" ~/.claude/agents/; done
```

Windows (PowerShell): copy instead of linking, and copy again after pulling updates.

```
git clone https://github.com/Artsdatabanken/clavis-pipeline
cd clavis-pipeline
pip install -r requirements.txt
Copy-Item -Recurse skills\* $HOME\.claude\skills\
Copy-Item agents\* $HOME\.claude\agents\
```

Start Claude Code in a folder that holds your sources, or in the repository with the sources elsewhere; the skills take paths.

## Running

Start Claude Code in the repository folder, on Opus, and name the taxon and the sources:

> Make a key for Soricidae from the PDFs in /path/to/sources, using species.csv there as the species list. Run straight through.

`build-clavis-key` takes over; its planner script tells it each phase. It spawns one harvester and one digitizer per source, one auditor per draft and one usability agent for the merged key, which is how the sources stay independent and no agent checks its own work.

Single steps by name: "audit key.json against its claims", "merge these three keys", "translate key.json to en", "did this key miss anything in the book".

## Models

**Opus runs the job, Sonnet does every agent's work.** Start Claude Code in this folder with Claude Opus 5.5 (`claude-opus-5-5`) as the session model; `.claude/settings.json` (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`) puts every sub-agent on Claude Sonnet 5.5 (`claude-sonnet-5-5`), and the agent files say `model: sonnet` as well. A sub-agent with no model set would otherwise run on the session's model. The orchestrator is where the judgment sits (page ranges, whether a harvester's "cannot be told apart" is what the book says, scripts that break on real data); the agents follow skills with checklists and scripts behind them.

### Models tested

All in Claude Code, October 2026, on the same job.

| Model | API id | Role tested | Verdict |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | running the job; all agents | best for running the job; as the agent model no better than Sonnet at three to five times the cost |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | all agents; running the job | the agent model; running the job on its own it made content mistakes (undid a correct look-alike rule, skipped confirming section pages) that cost two species pairs |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | harvester, one book, identical inputs to a Sonnet harvester | not usable: about half the claims, a fifth of its quotes not in the book, 12% of the book's words quoted against Sonnet's 39%, none of the structured fields filled, "usually" on almost every claim, claims for a species the book does not describe. Harvesting is the simplest model job in the pipeline, so Haiku is not used for any agent |
| Claude Fable 5.1 | `claude-fable-5-1` | not chosen; one sub-agent fell back to it once because no model was set | far more expensive per token than Opus, with nothing in this pipeline that needs it; the model settings above now prevent the fallback |

## Tokens and cost

Measured with this setup, October 2026, as logged by Claude Code (`tools/token_report.py`; it also writes `tokens.md` at the end of every run). Output counts in the transcripts look incomplete; Claude Code's `/cost` screen is authoritative for output. Input dominates the cost regardless: every call re-reads the agent's context from the cache.

**Five printed field guides (four of them scanned books) and one existing digital matrix key, 24 taxa:** 73 minutes, 21 agents.

| Model | Agents | Calls | Fresh input | Cache write | Cache read | Output (logged) | API cost |
|---|---|---|---|---|---|---|---|
| Opus 5.5 | orchestrator | 229 | 458 | 1.69 M | 46.0 M | 3.8 k | USD 17.73 |
| Sonnet 5.5 | 5 harvesters, 5 digitizers, 6 auditors, 1 refiner, 2 usability, 1 restarted | 1 114 | 2 250 | 5.30 M | 125.5 M | 11.0 k | USD 38.48 |
| total | 21 | 1 343 | 2 708 | 6.99 M | 171.6 M | 14.8 k | USD 56.21 |

Prices used (per million tokens, Claude API list prices on 2 October 2026): Opus 5.5 USD 4 input, 20 output, 0.20 cache read; Sonnet 5.5 USD 2 input, 10 output, 0.20 cache read; cache writes at 1.25 times input. Prices change; the token counts are what to compare.

**What it costs in practice.** On a Claude Max subscription (the USD 100 per month tier) several such runs fit in a day within the plan's limits, so the real cost per run is a few dollars at most. Check `/usage` before a run: a run uses a noticeable part of a 5-hour session budget, and pauses until the reset rather than failing if it runs out.

## Optional installs

- **Figures in scanned books.** A scanned book has one image per page, so figures can only be found by a layout model. Install Surya once in a local environment (needs a GPU for reasonable speed):

  ```
  uv venv --python 3.12 .venv
  uv pip install --python .venv surya-ocr
  ```

  Then, per scanned book: `.venv/bin/python tools/layout_pdf.py BOOK.pdf --pages <section> --out work/<source>/layout.json`, and pass `--layout work/<source>/layout.json` to `find_figures.py`. Without it the harvesters work from the text only.
- **Checking the skills against the Agent Skills specification:** `uv tool install skills-ref`, then `agentskills validate skills/<name>`.

## Known rough edges

- The skills say `python3`; on Windows use `python`.
- OCR needs Surya installed separately; without it, use a PDF that already has a text layer or supply page images plus text yourself.
- `vernacular.py` in the merge skill writes back into the key file it is given. Pass a copy if you want to keep the input untouched.
