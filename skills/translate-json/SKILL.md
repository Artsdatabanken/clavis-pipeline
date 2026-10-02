---
name: translate-json
description: Add a target language to a JSON file whose localized fields are objects keyed by ISO 639-1 codes (BCP47 short form). Deterministic Python scripts handle extraction, splicing, and validation — the model only produces target-language strings. Domain-agnostic and language-agnostic. Designed for Clavis identification keys but works on any schema using the language-keyed-object convention. Optionally consumes a glossary (hard constraints), reference texts (soft context), and a domain adapter (authoritative lookups, e.g. NBIC vernacular-name resolution). Use when the user wants to add a language to a JSON file ("translate this to en", "add German to this key", "make this multilingual").
license: MIT
compatibility: Python 3.11+. Network only when the vernacular-name adapter or urls.txt references are used.
metadata:
  author: Artsdatabanken
  version: "1.0"
  pipeline: clavis-pipeline
---

# Add a target language to a JSON document

**Never delete or overwrite the user's files.** Write new files; leave the originals in place and say in one line which are now redundant. Deleting is the user's call, even if a plan he approved said "replaces" or "absorbs".


This skill **does not write or rewrite JSON**. The model's only job is to translate already-extracted strings into the target language. Structural manipulation (walking the document, finding localizable fields, inserting target keys, validating against `$schema`) is done by Python scripts in `pipeline/`. Do not be tempted to emit the output JSON yourself — it is wasteful and risks structural drift.

## Inputs to gather (ask only if missing)

- **Input JSON path** — the source file. It must contain localized objects keyed by ISO 639-1 codes (e.g. `{"nb": "..."}`). If the file has a `$schema`, validation will run against it.
- **Source language code** — e.g. `nb`, `en`, `de`. Must match the existing keys in the localized objects.
- **Target language code** — e.g. `en`, `nn`, `es`.
- **Pipeline directory** — defaults to `./pipeline` (the scripts directory). Override with `PIPELINE_DIR=...` if installed elsewhere.
- **References directory** — defaults to `./references` (or whatever the user points at). Optional. May contain:
  - `glossary.tsv` — tab-separated `source<TAB>target` pairs. Treat as **hard constraints**: if the source string matches a glossary entry exactly, use the target verbatim. If it contains a glossary term as a substring, prefer the target term for that span.
  - `glossary_version` — single-line file naming the glossary revision (any string). Used to invalidate the translation cache when the glossary changes. If absent, the cache uses an empty string.
  - `reference_texts/` — directory of `.txt`/`.md` files in the target language. Treat as **soft context**: terminology and phrasing to imitate, not constraints.
  - `urls.txt` — one URL per line. Fetch each with WebFetch (cached for 15 minutes) and treat the content as reference text.
- **Domain adapter** — optional `pipeline/adapters/<name>.py` script. If the user mentions one (e.g. NBIC vernacular-name resolution), invoke it BEFORE the model step on the relevant subset of records.

## The pipeline

Run these in order from the project root. Each step produces a JSONL artifact under `work/`.

```bash
INPUT="<input.json>"; SOURCE="<src>"; TARGET="<tgt>"
mkdir -p work

# 1. Extract localizable strings (no model involved).
python3 -m pipeline.extract "$INPUT" --source "$SOURCE" \
    --out work/strings.jsonl --non-text-out work/non_text.jsonl
```

Each record in `strings.jsonl` is `{id, path, parent_path, field, kind, source, context}`. `non_text.jsonl` lists language-keyed objects whose values are non-string (e.g. `localizedUrl` references) — these are skipped by the translator path and need a domain adapter if they should be localized too.

```bash
# 2. Run domain adapters (only when the input file's domain has one configured).
#    Adapters resolve records that should NOT be model-translated — vernacular
#    species names, place-name authority lookups, etc. They run BEFORE the model
#    so we don't pay for translations we could have looked up.
#
#    Vernacular-name adapter (for Clavis / biological taxa). Cascades through:
#      NBIC (Artsdatabanken) → Sweden Artdatabanken (sv only) → GBIF →
#      Wikispecies interwiki → iNaturalist. Stops at the first authoritative hit.
#      Caches results per (scientificName, target_lang) in adapter_cache.json.
#      Filters out cross-language data-quality collisions (e.g. GBIF entries with
#      the source-language name mis-tagged as target).
#      Set ARTDATABANKEN_TOKEN env var to enable the Swedish endpoint.
python3 -m pipeline.adapters.vernacular_names work/strings.jsonl \
    --target "$TARGET" \
    --out-resolved work/adapter_resolved.jsonl \
    --out-remainder work/adapter_remainder.jsonl \
    --cache work/adapter_cache.json --sleep 0.1
# The adapter emits records of kind=vernacular_name to adapter_resolved.jsonl
# when a hit was found, OR to adapter_remainder.jsonl when not (with an
# adapter_trace field listing which sources were tried). Non-vernacular records
# pass through unchanged into adapter_remainder.jsonl.
INPUT_FOR_CACHE_FILTER=work/adapter_remainder.jsonl
```

If no domain adapter applies, set `INPUT_FOR_CACHE_FILTER=work/strings.jsonl` and skip the adapter call entirely.

```bash
# 3. Cache filter — skip strings whose (source, context, target_lang, glossary_version)
#    triple already has a stored translation. Operates on the adapter remainder
#    (or strings.jsonl directly if no adapter ran).
GV=$(cat references/glossary_version 2>/dev/null || echo "")
python3 -m pipeline.cache filter "$INPUT_FOR_CACHE_FILTER" \
    --target "$TARGET" --cache work/cache.jsonl --glossary-version "$GV" \
    --out-todo work/todo.jsonl --out-resolved work/cache_resolved.jsonl
```

After step 3, `work/todo.jsonl` contains exactly the records that need a fresh model translation. Everything else lives in `work/cache_resolved.jsonl` (from prior runs) and `work/adapter_resolved.jsonl` (from the domain adapter, if one ran).

## The model step (the only AI work)

This is where you, the model, do your one job: produce a target-language string for each record in `work/todo.jsonl`.

**Inputs to load before translating**:
1. `work/todo.jsonl` — the records you must translate.
2. `references/glossary.tsv`, if present — read into a `source → target` dict.
3. `references/reference_texts/*` — read each file; treat as background.
4. `references/urls.txt`, if present — fetch each URL with WebFetch, get a concise extraction of domain terminology, store as reference text.

**Translation rules** (apply in priority order):
1. **Glossary hard match**: if `source` equals a glossary key (case-insensitive), `target` MUST be the glossary value.
2. **Looks-like-scientific-name**: if `source` is a Latin binomial or higher taxon (capitalized first word, second word lowercase, or a single capitalized Latin word ending in `-aceae`/`-idae`/`-ales`/`-aria`/`-ina`/etc.), copy source to target unchanged. Flag with `"unchanged_reason": "scientific_name"`.
3. **Use context**: `record.context.parentTitle` (the parent character/section), `record.context.scientificName` (the taxon), and `record.kind` (`vernacular_name`/`title`/`description`) all shape the translation. Sibling state titles under the same character should share parallel phrasing.
4. **Soft context**: prefer terminology found in `reference_texts` when alternatives exist.
5. **Uncertainty**: if you cannot produce a confident translation (e.g. an obscure vernacular name with no authoritative English form), set `target` to `null` and add `"needs_review": true` with a short `"note"`. Do NOT invent plausible-sounding fakes — null beats wrong.

**Batching**: group records by `context.parentTitle` (or `context.scientificName`) so that sibling states stay coherent. For a small file (< 200 records, < 30 KB of source text), a single request is fine. For larger files, chunk by character/section.

**Output format**: write `work/translations.jsonl`, one line per input record, each carrying `path`, `source`, `target`, and `cache_key` (copy from the todo record). Optionally include `needs_review` and `note`.

## After the model step

```bash
# 4. Persist new translations to the cache for next time.
python3 -m pipeline.cache store work/translations.jsonl \
    --target "$TARGET" --cache work/cache.jsonl --glossary-version "$GV"

# 5. Merge everything that has a target into a single splice input.
#    (Filter out any records where target is null — those go in a review report.)
python3 -c "
import json, pathlib
out, review = [], []
for src in ['work/cache_resolved.jsonl', 'work/adapter_resolved.jsonl', 'work/translations.jsonl']:
    p = pathlib.Path(src)
    if not p.exists(): continue
    for line in p.read_text(encoding='utf-8').splitlines():
        if not line.strip(): continue
        rec = json.loads(line)
        (out if rec.get('target') is not None else review).append(rec)
pathlib.Path('work/all_translations.jsonl').write_text(
    '\n'.join(json.dumps(r, ensure_ascii=False) for r in out) + ('\n' if out else ''), encoding='utf-8')
pathlib.Path('work/needs_review.jsonl').write_text(
    '\n'.join(json.dumps(r, ensure_ascii=False) for r in review) + ('\n' if review else ''), encoding='utf-8')
print(f'{len(out)} ready to splice, {len(review)} need review')
"

# 6. Splice into a new output file.
OUT="${INPUT%.*}.${TARGET}.json"
python3 -m pipeline.splice "$INPUT" work/all_translations.jsonl \
    --source "$SOURCE" --target "$TARGET" --out "$OUT"

# 7. Validate the output against $schema, with the input as a baseline so only
#    NEW errors (introduced by the splice) cause a non-zero exit.
python3 -m pipeline.validate "$OUT" --baseline "$INPUT"
```

If step 7 reports new errors, do NOT report the task as complete — inspect the new errors first. They indicate the splice broke something the input didn't already break.

## Reporting back to the user

Tell the user, briefly:
- The output path.
- A breakdown: model / cache / adapter / null (needs review). For the adapter,
  include the source breakdown the adapter prints (e.g. "3 via GBIF, 2 via
  iNaturalist") — it tells the user how trustworthy the resolved set is.
- How many records ended up in `needs_review.jsonl` and why.
- Whether validation introduced any new errors compared to the baseline.

Do NOT print the translations themselves — they're in the output file, which the user can open.

## Adapter trace

For each record the adapter rejected, `adapter_remainder.jsonl` carries an
`adapter_trace` field listing each source tried and how it ended:
`nbic_no_target_lang`, `gbif_no_match`, `wikispecies_no_match`, etc. Suffix
`_collision` means the source returned the source-language string and was
discarded as a data-quality issue. Use this trace when the user asks why a
specific vernacular name wasn't auto-resolved.

## What not to do

- Do not write the output JSON yourself. Use `pipeline.splice`.
- Do not edit the input JSON. The pipeline produces a new file.
- Do not skip the glossary check just because a string "looks easy". A glossary entry is a hard constraint that overrides your judgment by design.
- Do not invent vernacular names, place names, or domain-specific common names when uncertain. Set `target: null` and let the user fill it in.
- Do not translate `scientificName` fields. They are Latin and the extractor already excludes them.
- Do not try to translate `localizedUrl` entries (per-language URL references). They show up in `non_text.jsonl` for a separate adapter to handle.
