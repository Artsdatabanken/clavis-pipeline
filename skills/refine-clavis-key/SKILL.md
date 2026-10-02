---
name: refine-clavis-key
description: Clean up a Clavis JSON file produced by a structured-source transcoder (matrix → Clavis, dichotomous-key web scrape → Clavis, etc.). Operates entirely on Clavis structure — no source material required. Domain-agnostic and language-agnostic. Merges duplicate characters, merges synonymous states within a character, splits bundled states into atomic states with paired uncertain frequencies, infers taxonomic hierarchy, and hoists statements to the highest applicable taxon. Use after running `matrix_to_clavis.py` or any other Clavis transcoder, or when a hand-written Clavis is suspected of needing structural cleanup. Not a replacement for `digitize-clavis-key` — that skill already does this work inline when reading source prose.
license: MIT
compatibility: Python 3.11+. No network.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Refine a Clavis identification key

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant. Deleting is the user's call, even if a plan he approved said "replaces" or "absorbs".


This skill cleans up a Clavis JSON file. It runs after a *transcoder* has converted some structured source (a matrix-key web app, a dichotomous-key viewer, an exported spreadsheet, a hand-written draft) into Clavis. The transcoder is dumb and lossless — it preserves whatever the source says without trying to be smart. This skill makes the Clavis good.

For source-prose digitization (PDFs, scans, printed keys), use `digitize-clavis-key` instead — that skill does this work inline because it has source context.

## Design principle: script first, AI for judgment only

Every phase has the same shape: a deterministic *narrow* script that surfaces candidates, an AI step that judges only those candidates, and a deterministic *apply* script that commits the decisions. AI compute is expensive — never re-derive what code can compute. If you find yourself eyeballing a list to spot patterns, that's a script you haven't written yet. Pre-filter, rank, structure with code. The model only judges what code couldn't classify.

When extending: build the *narrow* script first (cheapest), then *apply*, then write the SKILL.md guidance that tells Claude what to look for in the candidates. Building *apply* first produces a script that takes hand-written decisions instead of script-narrowed ones — defeats the point.

## Inputs to gather (ask only if missing)

- **Path to the input Clavis JSON** (typically the output of a transcoder).
- **Path for the output** (default: alongside input, suffixed `_refined`).

## Phases — run in order

Each phase's output is the next phase's input. **Order matters.** Taxonomy operations come last because earlier passes shift which assertions belong at which level: a hoisted statement could be stranded after a state split or character merge moves the assertion's centre of gravity.

### Phase 0 — Couplets: one path per taxon

A transcoded dichotomous key encodes couplet steps as characters whose states are whole sentences. Decompose them **per taxon along its own path through the key**: for each taxon, collect the couplet halves it passed through, split each half into its single-trait assertions, and only then build characters from the assertions. Combining couplets by text across taxa (all "size" clauses from every step into one character) widens measurement ranges beyond what the source says for any one taxon; the rodent run had to redo the artfakta key for exactly this. Measurements from couplets become numerical characters with the taxon's own range.

### Phase 1 — Character-title merge (script only)

> **Two cautions when the input is a cross-source merge rather than one
> transcoder's output.** Phase 1 was built for duplicate titles produced by *the
> same observer* repeated across couplets, where accumulating by union is correct.
> Feed it several independent sources and (a) its union of asserted states drags a
> precise source down to an imprecise one's uncertainty, and (b) its
> union-of-breakpoints rebinning fragments quantitative characters. Resolve
> cross-source cells to one assertion per `(taxon, character)` *before* running
> Phase 1, so its union is a no-op.

`scripts/refine_clavis.py IN.json --out OUT.json`

Merges characters whose primary-language titles are byte-equal:
- **Categorical groups** — union of states by label; states with new labels join the canonical character.
- **Quantitative groups** — every state label parses as a numeric range/value, so the script computes the union of breakpoints across all chars in the group and emits atomic bins between consecutive breakpoints. A taxon that asserted `5-19 mm` now asserts atoms `5-9 mm`, `10-14 mm`, `15-19 mm` with paired 0.5s.

Statements re-emitted to honour the frequency rule. No model judgment.

Skip this phase only if the input already has unique character titles.

### Phase 2 — Synonymous-state merge (script + AI)

Within a single character, merge states that name the same observable but with different wording (*pale yellow* / *yellowish-white*; *bruin* / *bruinachtig*; *truncated* / *truncate*).

**Narrow:** `scripts/find_state_merge_candidates.py IN.json --out candidates.md`

Surfaces, per character, every state pair where any of: token Jaccard ≥ 0.5, edit distance ≤ 4, or one label is a substring of the other. The script enumerates exhaustively — do not propose merges outside what it surfaced.

**Judge:** Read `candidates.md` and for each row decide:
- **Merge** — the two labels name the same observable a careful field worker can't reliably tell apart on a real specimen.
- **Keep** — the labels are genuinely distinguishable (e.g. *bruin* vs *donkerbruin* is two states; *5-9 mm* vs *5-10 mm* is the boundary problem Phase 1 already resolved for byte-equal titles, but if it slipped through it's a real conflict that Phase 4 may handle).

Default to keep when in doubt. Wrong merge loses identification resolution; wrong keep is recoverable.

Decisions JSON shape:
```json
{
  "merges": [
    {
      "character_id": "character:abc...",
      "kept_state_id": "state:wxyz...",
      "removed_state_ids": ["state:1111...", "state:2222..."]
    }
  ]
}
```

The kept state's label is preserved as-is. If you want the surviving label to combine information from both inputs (e.g. `pale yellow / yellowish-white`), edit the kept state's title in the output Clavis afterward — `apply_state_merges.py` doesn't relabel.

**Apply:** `scripts/apply_state_merges.py IN.json decisions.json --out OUT.json`

Drops removed states from each character; re-points every statement that referenced a removed state to the kept state; re-emits valid frequency-rule shapes.

### Phase 3 — Bundled-state split (script + AI)

A state label that combines distinguishable values (*red, sometimes white*; *gehakkeld of glad*; *wing length 8 or 12 mm*) violates Protocol 1 from the digitize/audit skills: a careful observer can tell the bundled values apart. Split such states into atomic states; re-encode any taxon that asserted the bundle as paired 0.5/0.5/... on the atomic states.

**Narrow:** `scripts/find_bundled_states.py IN.json --out bundles.md`

Flags state labels containing language-appropriate disjunction or qualification markers (English *or* / *sometimes* / *rarely*; Dutch *of* / *soms* / *zelden*; German *oder* / *manchmal* / *selten*; Norwegian *eller*; etc.), slashes, or commas in long labels. Each flagged state is reported with its character title and its full sibling-state list (for context — a split's atomic labels often reuse existing sibling labels). The script reads the language from `clavis["language"][0]`; add new entries to the `DISJUNCTIONS` / `QUALIFIERS` tables for unsupported languages.

**Judge:** Read `bundles.md`. For each flagged state decide:
- **Split** — the label combines distinguishable values; provide the atomic labels.
- **Keep** — the label is one observable, the connector is a clarifier, or splitting would lose co-occurrence information (e.g. `geel, zwart en rood` describes a *combined* color pattern; splitting into atoms says "yellow OR black OR red" which is wrong).

Multi-axis bundles (`[A] *and* [B]` where A and B are different traits, e.g. *long with red stripes*) belong to a future *character-split* phase, not here. Phase 3 splits within one character only.

Decisions JSON shape:
```json
{
  "splits": [
    {
      "state_id": "state:abc...",
      "atomic_labels": ["bruin", "grijs"]
    }
  ]
}
```

If an atomic label matches an existing sibling state's label, the apply step reuses that state ID. Otherwise it creates a new state with a fresh ID. Taxa that asserted the bundled state are re-encoded as paired 0.5s on the atomic states.

**Apply:** `scripts/apply_state_splits.py IN.json decisions.json --out OUT.json`

### Phase 4 — Multi-axis character split (script + AI)

A character represents **one** observable axis. If its states span multiple axes — e.g. color states (`groen`, `bruin`) sitting alongside pattern states (`met twee prominente vlekken`, `gevlekt`), or proportion states (`breder dan lang`) sitting alongside cross-profile states (`dakvormig`) — a specimen in hand can legitimately satisfy one state on each axis, and the user has no way to pick "the" state. The character is **bundled at the character level** and must split into one character per axis.

This is Protocol 1 applied at the character level. Don't dismiss as "borderline" — it makes the key unusable.

**Narrow:** `scripts/find_multi_axis_characters.py IN.json --out multi_axis.md`

Heuristic flags any character where: at least one state has a modifier prefix (Dutch *met*, English *with*, German *mit*, Norwegian *med*, …) and at least one sibling is a bare term; or compound vs simple state-label mix in a character of 4+ states; or large length spread (max ≥ 4× min, with min ≤ 5 chars); or **multi-clause prose** (≥2 states each ≥40 chars with ≥2 semicolons or ≥3 commas, typical of dichotomous-key couplets transcoded verbatim where every state bundles many axes in one sentence). Quantitative characters (all-numeric state labels) are skipped.

**Judge:** For each flagged character, decide:
- **Split** — identify the underlying axes; specify N new characters with their state lists; map each original state to one or more (new_char, new_state) pairs. A state like `'groen met vele kleine stippels'` decomposes into `Basiskleur=groen` + `Patroon=met vele kleine stippels`.
- **Tier-3 keep** — the character is single-axis under the framing "X if present, else absent" (e.g. `'afwezig'` alongside shape descriptors). Acceptable.
- **Plain keep** — false positive (compound labels of one axis, e.g. geographic regions named "zandgronden Midden-Nederland", or month abbreviations).

When designing a split:
- Don't lose information. Every original assertion should map to at least one new-char assertion.
- A state that *only* describes one axis maps to that axis only — leave the other axes unspecified for that taxon (they remain unknown, which is honest).
- If an axis has only one positively-asserted state in the source, add an explicit "default" state (e.g. `'niet naar achteren verlengd'`) so the new character has ≥2 states. The default receives no assertions.
- Compound source states like `'X met Y'` decompose into one assertion per axis: `axis1=X` AND `axis2=Y`.

Decisions JSON shape:
```json
{
  "character_splits": [
    {
      "original_character_id": "character:abc...",
      "new_characters": [
        {"title": "Lichaam — Basiskleur",
         "states": ["bruin", "zwart", "groen", ...]},
        {"title": "Lichaam — Patroon",
         "states": ["eenkleurig", "gevlekt", "met twee prominente vlekken", ...]}
      ],
      "state_mapping": {
        "<original_state_id>": [
          {"new_char_index": 0, "new_state_label": "groen"},
          {"new_char_index": 1, "new_state_label": "met vele kleine stippels"}
        ]
      }
    }
  ]
}
```

**Apply:** `scripts/apply_character_split.py IN.json decisions.json --out OUT.json`

> **This script also flattens graded frequencies.** Like `refine_clavis.py`, it
> re-emits each group as confident-or-paired-0.5, so an input carrying deliberate
> values such as 0.95/0.05 comes out as 0.5/0.5. Record which statements carry
> graded frequencies before running any apply step, and restore them afterwards.

Drops original chars; creates new chars with fresh IDs and state IDs; re-points every original assertion to the new (char, state) pairs in the mapping; re-emits valid frequency-rule shapes; sets every character's `type` to `exclusive`, which is the normal choice for a key — but note the schema also allows `non-exclusive` and `numerical`, and a measurement is better held in a `numerical` character than binned into states.

**After applying splits, re-run Phase 1** (`refine_clavis.py`) on the output before continuing. Multi-axis splits routinely produce sub-character titles like "Body coloration" / "Max body length" / "Distribution" that recur across many couplets in a dichotomous key — re-running Phase 1 collapses them into one canonical character per axis.

### Phase 5 — Hierarchy inference (script only)

Group flat species lists into the genera implied by their binomials. The script auto-applies — pure binomial parsing, no judgment needed for the standard case. If you ever need to override (subgenus distinctions, weird author-string parsing, manual family-level placement), edit the output Clavis directly or pre-process the taxa tree before invoking this phase.

`scripts/infer_hierarchy.py IN.json --out OUT.json`. For each parent in the taxa tree, groups its species children by the leading capitalised word of `scientificName`; where ≥2 species share a genus, wraps them in a new genus taxon node with `scientificName: <genus>`.

Statements stay where they are (still on species). Phase 6's hoister moves them up where appropriate.

### Phase 6 — Statement hoisting (script only)

Bottom-up: for each (parent, character) where every direct child has the same explicit asserted-state set, lift the assertion to the parent and remove the children's copies. Children inherit from the parent (Clavis lookup convention).

`scripts/hoist_statements.py IN.json --out OUT.json`.

> **Flattens graded frequencies, like the other apply scripts.** It re-emits from
> the post-hoist asserted map as confident-or-paired-0.5, so any deliberate value
> outside {0, 0.5, 1} is lost. If the input carries graded frequencies, hoist by
> lifting whole frequency vectors instead (a parent takes the children's shared
> vector verbatim), or restore them afterwards.

A child that has *no* explicit assertion on a character blocks hoisting at that level — there's no way to know what value it should inherit once the parent commits. So sparse-assertion characters mostly stay where the transcoder put them.

Statements are re-emitted from the post-hoist asserted map so the frequency-rule shape stays valid.

### Phase 7 — Verify

Run `tools/verify.py` (repository root) on the final output. Confirm: parses, IDs unique, frequency-rule shapes valid, leaf vectors discriminable.

The verifier currently assumes every taxon has `scientificName`; refined Clavis files often have label-only taxa (variations, family containers). For those, the user has a project-local `spot_check_clavis.py` that's tolerant. Either fork the verifier here with the same tolerance or use the spot-check version.

If discriminability fails, that's a structural alarm — earlier passes over-merged states or hoisted too aggressively. Don't paper over by inventing characters; track down which pass is responsible.

## Implementation status

| Phase | Narrow | Judge | Apply |
|---|---|---|---|
| 1 (char-title merge) | n/a (script-only) | — | ✅ |
| 2 (synonym merge) | ✅ | ready | ✅ |
| 3 (bundle split — state level) | ✅ | ready | ✅ |
| 4 (multi-axis split — character level) | ✅ | ready | ✅ |
| 5 (hierarchy) | ✅ (auto-applies) | not needed for clean case | ✅ |
| 6 (hoisting) | n/a (script-only) | — | ✅ |
| 7 (verify) | reuse audit | — | n/a |

## Hand-off

After Phase 5/6, the refined Clavis is ready for `audit-clavis-key`. The audit skill catches *source-vs-Clavis* mismatches (Protocol 1/2 violations the source itself reveals, missing characters from descriptions, etc.) — separate from the structural cleanup this skill does. Always run audit after refine, never instead of it.
