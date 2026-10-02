# Local models

Untested. This page records the intended path so someone can try it and report back with `TEMPLATE.md`.

## Shape

Nothing in the skills depends on a particular model or vendor; a skill is a markdown instruction set plus Python scripts. A local run therefore needs:

1. A local inference server with an OpenAI-compatible endpoint: llama.cpp's `llama-server`, Ollama, vLLM, or similar.
2. A harness that reads `AGENTS.md`, can run shell commands, and can be pointed at that endpoint. Candidates: OpenCode, Aider, Goose, Cline.
3. A model with vision if you want the digitize step to read figure labels from page images. Without vision, the pipeline still runs on OCR text, but the figure-label check in the digitize and audit skills cannot be done.

## How to tell whether a local model is good enough

Run its harvest on one book and compare with the Sonnet harvest of the same book (`claude-code.md` shows the Haiku comparison). `harvest-claims/scripts/source_coverage.py` gives the numbers that matter without anyone reading the claims: how many quotes are found word for word in the book, what share of the book's words ended up quoted, how many unquoted stretches remain. Please send the result, good or bad.

## Expectations

Refine, merge, translate and verify are mostly scripts and should work with small models. Digitize and audit are where a model has to read forty pages of a 1970s flora and make consistent judgments; expect small models to miss traits and to bundle states, which the audit step is designed to catch but cannot fully fix. Report what you see.

## Not in scope yet

A typed decision layer (small local models answering fixed yes/no or pick-one questions, with calibrated confidence) is being tested separately and is not part of this repository.
