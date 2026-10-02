# <Harness name>

Copy this file to `guides/<harness>.md` and fill it in from an actual run. Short, factual, observed. Delete the hints in angle brackets.

## Setup

- Harness and version: <e.g. Codex CLI 0.9.2>
- Model: <exact model id>
- Platform: <Linux / macOS / Windows, Python version>
- How the harness was pointed at this repository: <cloned and opened? AGENTS.md picked up automatically? skills pasted as system prompt?>
- Sub-agents available: <yes / no; if no, how did you keep sources separate?>

## The job

- Taxon and number of species: <>
- Sources: <type only: scanned book from a national library, modern PDF field guide, matrix export, existing Clavis file. No titles needed if the source is not public.>
- Date: <>

## Gate results

<Paste `leveranse/gates.md`: pairs separated, claims audit and source coverage per source, round-trip.>

## What happened, per step

| Step | Result | Notes |
|---|---|---|
| species list | worked / partly / failed / skipped | <> |
| digitize | | <> |
| audit | | <> |
| refine | | <> |
| merge | | <> |
| verify | | <> |
| translate | | <> |

## Changes needed

<Any SKILL.md or script that had to be changed to work. Include the diff in the pull request.>

## Cost and time

- Wall-clock time: <>
- Per model: model id, which agents ran on it, calls, input, cache write, cache read and output tokens: <>
- API-equivalent cost on the date of the run, with the prices used: <>
- What it cost you in practice (subscription, local hardware, energy if you know it): <>

## Would you run it again this way?

<One paragraph.>
