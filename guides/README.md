# Guides per harness and model

One file per way of running the pipeline. "Validated" means the maintainers ran a full book-to-key job with it. "Reported" means a user sent in a filled `TEMPLATE.md`. Anything else is untested; the skills are harness-neutral, so it will probably work, but nobody has checked.

| Harness | Model | Status | Guide |
|---|---|---|---|
| Claude Code | Opus 5.5 orchestrating, Sonnet 5.5 agents | Validated, recommended | `claude-code.md` |
| Claude Code | Sonnet 5.5 throughout | Validated, cheaper, slightly weaker keys | `claude-code.md` |
| Claude Code | Opus 5.5 throughout | Validated, 3 to 5 times the cost, no better | `claude-code.md` |
| Claude Code | Haiku 4.5 as harvester | Tested, not usable | `claude-code.md` |
| Codex, Cursor, Gemini CLI, Aider, OpenCode, Goose, others | any | Untested | send a `TEMPLATE.md` |
| Local model behind an OpenAI-compatible server | any | Untested | `local.md` |

## Please report what you try

The aim is a pipeline that makes good keys with as little compute as possible: the smallest models that do the job, the fewest tokens, the shortest runs. Every model and harness someone tests moves that forward, including the ones that fail; a clear "this did not work, and here is where" is as useful as a success.

To add a guide: copy `TEMPLATE.md`, name it after the harness and model, fill it in from a real run (the gate table, tokens per model and wall-clock are the numbers that let runs be compared), and open a pull request. Keep it to what you observed. A cheap first test is one book's harvest compared with the Sonnet harvest of the same book, as in `claude-code.md`.
