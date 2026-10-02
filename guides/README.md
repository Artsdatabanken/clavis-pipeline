# Guides per harness and model

One file per way of running the pipeline. "Validated" means the maintainers ran a full book-to-key job with it. "Reported" means a user sent in a filled `TEMPLATE.md`. Anything else is untested; the skills are harness-neutral, so it will probably work, but nobody has checked.

| Harness | Model | Status | Guide |
|---|---|---|---|
| Claude Code | Claude Opus 4.7 to 5.5 | Validated | `claude-code.md` |
| Claude Code | Claude Sonnet 5.5 | Untested, recommended default once checked | `claude-code.md` |
| Codex, Cursor, Gemini CLI, Aider, OpenCode, Goose, others | any | Untested | send a `TEMPLATE.md` |
| Local model behind an OpenAI-compatible server | any | Untested | `local.md` |

To add a guide: copy `TEMPLATE.md`, name it after the harness, fill it in from a real run, open a pull request. Keep it to what you observed.
