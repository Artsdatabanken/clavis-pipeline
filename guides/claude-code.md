# Claude Code

The harness the pipeline was built and validated on.

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

Name the taxon and the sources:

> Make a key for Soricidae from the two PDFs in ./sources and this nb.no link: <url>

`build-clavis-key` takes over. It spawns one `clavis-digitizer` sub-agent per source and one `clavis-auditor` per draft, which is how the sources stay independent. It pauses once after the per-source drafts unless you tell it not to.

Single steps by name: "audit key.json against sources/book.pdf", "merge these three keys", "translate key.json to en".

## Model

Every agent in a run must use the model the run was started with, and nothing more expensive. Three layers enforce it under Claude Code:

1. `agents/*.md` carry `model: opus`, so a sub-agent spawned without an explicit model does not fall back to the main conversation's model. (That fallback is what happened on 1 October 2026: one nested agent ran half its calls on Claude Fable 5.1, five times the price, because neither the definition nor the spawn named a model.)
2. `.claude/settings.json` in this repository sets `CLAUDE_CODE_SUBAGENT_MODEL=opus` with `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, which makes Claude Code ignore every other model setting for sub-agents when it is started in this folder.
3. The build skill tells the orchestrator to pass the run's model on every spawn.

To run on another model (Sonnet 5.5 for the comparison), change the value in `.claude/settings.json` and in the three agent files; nothing else.

Validated on Claude Opus 5.5 (full rodent run, 1 October 2026) with the pipeline as it was then; the current version (claims-driven digitization, numerical characters, determinability pass, gate runner) has not had its first full run yet. Claude Sonnet 5.5 (`claude-sonnet-5-5`) is the intended cheaper default once compared on the same job. Whatever the model, use the default effort or higher for digitize and audit; those are the judgment-heavy steps. Refine, merge and translate are mostly scripts and tolerate a cheaper setting.

Vision matters: the digitizer reads page images directly to catch the labels around figures that OCR drops. All current Claude models have it.

### Haiku: tested, not used

On 2 October 2026 one book (Gibson, 24 species) was harvested by Haiku 4.5 and by Sonnet 5.5 with identical inputs and instructions. Haiku: 298 claims, 61 quotes not in the book, 12% of the book's words quoted, none of the structured fields filled (numbers, diagnostic traits, comparisons), "usually" on almost every claim, and claims for a species the book does not describe. Sonnet: 584 claims, every quote found, 39% of the words quoted, all fields used. Saving: USD 1.30 per book. Harvesting is the simplest model job in the pipeline, so Haiku is not used for any agent.

## Cost and time

Measured, 1 October 2026, Rodentia for Norway, 29 species on the list, 24 covered, five scanned books plus one transcoded matrix key, Claude Opus 5.5 for the agents: 93 minutes wall-clock, 25 agent transcripts, 1681 model calls, 229 M cache-read tokens, 12.8 M cache-write tokens, 111 k output tokens, about USD 120 at list prices (`tools/token_report.py`). Roughly USD 5 per covered species, almost all of it input re-read from cache across the per-taxon harvest and per-source digitize and audit agents. The cuts listed in `TODO.md` target exactly that.

## Known rough edges

- The skills say `python3`; on Windows use `python`.
- OCR needs Surya installed separately; without it, use a PDF that already has a text layer or supply page images plus text yourself.
- `vernacular.py` in the merge skill writes back into the key file it is given. Pass a copy if you want to keep the input untouched.
