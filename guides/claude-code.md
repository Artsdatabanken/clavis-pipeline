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

**Recommended: Opus orchestrates, Sonnet does every agent's work.** Start Claude Code in this folder with Opus as the session model; `.claude/settings.json` (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`) forces every sub-agent onto Sonnet, and the agent files say `model: sonnet` as well. The orchestrator is where the judgment sits (page ranges, catching harvesters that mark "very similar" as "cannot be told apart", fixing scripts that break on real data); the agents follow skills with checklists and scripts behind them.

Tested with, all in Claude Code on Linux, October 2026:

| Model | API id | Role tested | Verdict |
|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | orchestrator; all agents (runs 2, 3) | best orchestrator; as agents good but 3 to 5 times the cost |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | all agents; orchestrator (run 4) | the agent model; as orchestrator it makes more wrong calls on its own |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | harvester, one book | not usable: half the claims, a fifth of its quotes not in the book, structured fields ignored |
| Claude Fable 5.1 | `claude-fable-5-1` | none on purpose; one nested agent fell back to it once | too expensive for this work; the model settings prevent it |

### The comparison runs

All on the same job: a key to 24 species built from five printed field guides (four of them scanned books) and one existing digital matrix key, 2 October 2026 unless noted.

| Run | Models | Pairs not separable (of 276) | Characters | Wall-clock | API-equivalent cost |
|---|---|---|---|---|---|
| 2 (1 Oct, older pipeline) | Opus throughout | 1 | 84 (bins) | 93 min | USD 119 |
| 3 | Opus throughout | 2 | 86 | ~5 h (paused at a spend limit) | USD 173 |
| 4 | Sonnet throughout | 3 | 74 | 85 min | USD 36 |
| 5 | Opus orchestrator, Sonnet agents | 1 (the two beavers; no source separates them) | 81 | 73 min | USD 56 |

Run 5's key also passes the check of every claim against the books (every quote word for word in its book, every unquoted stretch of the harvested pages read and decided), which runs 2 to 4 did not have.

### Tokens per model, run 5

As logged by Claude Code (`tools/token_report.py`). Output counts in Claude Code's transcripts look incomplete; the `/cost` screen is authoritative for output. Input dominates the cost regardless: every call re-reads the agent's context from the cache.

| Model | Agents | Calls | Fresh input | Cache write | Cache read | Output (logged) | API cost, 2 Oct 2026 |
|---|---|---|---|---|---|---|---|
| Opus 5.5 | 1 orchestrator | 229 | 458 | 1.69 M | 46.0 M | 3.8 k | USD 17.73 |
| Sonnet 5.5 | 20 (5 harvesters, 5 digitizers, 6 auditors, 1 refiner, 2 usability, 1 restarted) | 1 114 | 2 250 | 5.30 M | 125.5 M | 11.0 k | USD 38.48 |
| total | 21 | 1 343 | 2 708 | 6.99 M | 171.6 M | 14.8 k | USD 56.21 |

Prices used (per million tokens, Claude API list prices on 2 October 2026): Opus 5.5 USD 4 input, 20 output, 0.20 cache read; Sonnet 5.5 USD 2 input, 10 output, 0.20 cache read; cache writes at 1.25 times input. Prices change; the token counts are what to compare. They are in `tools/token_report.py` and the final report of every run states both.

**What it costs in practice.** The dollar figures are what the same tokens would cost through the API. On a Claude Max subscription (the USD 100 per month tier) several such runs fit in a day within the plan's limits, so the real cost per run is a few dollars at most (the maintainer's estimate: under USD 3). Check `/usage` before a run: a run uses a noticeable part of a 5-hour session budget, and pauses until the reset rather than failing if it runs out.

### Why not other settings

- **All Opus**: three to five times the cost of the recommended setting, no better keys.
- **All Sonnet**: cheapest, but the orchestrator made content mistakes (undid a correct look-alike rule, skipped confirming section pages) that cost two species pairs.
- **Haiku anywhere**: the harvest comparison (one book, identical inputs): Haiku 298 claims, 61 quotes not in the book, 12% of the book's words quoted, none of the structured fields filled, "usually" on almost every claim, claims for a species the book does not describe; Sonnet 584 claims, every quote found, 39% quoted, all fields used. Harvesting is the simplest model job here, so Haiku is not used for any agent.
- **Model fallback**: a sub-agent with no model in its definition and none at spawn runs on the main session's model. That is how one agent ran on Fable 5.1 on 1 October. The agent files and the settings now prevent it.

Vision matters for figure labels: the harvester reads figure crops. All current Claude models have vision; Haiku's harvest produced no figure claims.

## Known rough edges

- The skills say `python3`; on Windows use `python`.
- OCR needs Surya installed separately; without it, use a PDF that already has a text layer or supply page images plus text yourself.
- `vernacular.py` in the merge skill writes back into the key file it is given. Pass a copy if you want to keep the input untouched.
