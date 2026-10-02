# Claim, provenance and skipped-claim formats

Part of the `harvest-claims` skill. All files are JSON lines, UTF-8, one object per line.

## claims.jsonl

| Field | Who sets it | Meaning |
|---|---|---|
| `id` | `check_claims.py` | `claim:` plus a hash of source, taxon, trait, value and page (normalized). Stable across re-runs. |
| `source` | harvester | Short name of the source, identical on every line from it (e.g. `lid2005`). |
| `taxon` | harvester | Scientific name as the source writes it. Resolution to accepted names happens later. |
| `trait` | harvester | What is observed, in the source language, short: `halelengde`, `bukfarge`, `antall tenner`. |
| `value` | harvester | What the source says about it, as stated: `lengre enn kroppen`, `20–35 g`, `hvit`. One value per claim. |
| `qualifier` | harvester, else `check_claims.py` from the quote | `always`, `usually`, `sometimes`, `rarely`, `range`, `comparative`, `unspecified`. |
| `quote` | harvester | The verbatim passage or figure label the claim rests on. |
| `page` | harvester | Printed page number, or plate/figure id. |
| `kind` | harvester | `description`, `key`, `table`, `figure`. Default `description`. |
| `observable` | harvester | `false` for traits that cannot be seen on a specimen or find. Default `true`. |
| `value_num` | `check_claims.py` | `[min, max]` parsed from `value`; `null` on an open side (`over 24 mm` → `[24, null]`). |
| `unit` | `check_claims.py` | Unit parsed from `value` (`mm`, `g`, `%`). |
| `diagnostic` | harvester, else `check_claims.py` | `true` when the source presents the trait as what distinguishes the taxon (a key couplet, or wording like "skilles fra ... ved"). The digitizer scores the other taxa absent on that character. |
| `same_as` | harvester | Scientific name of a taxon this one cannot be told from, per the source ("ingen ytre forskjeller fra ..."). The digitizer copies that taxon's values where this one has none. `trait` and `value` describe the statement itself. |
| `note` | `check_claims.py` | Something the harvester must fix, e.g. a quote with two frequency words, or a look-alike quote without `same_as`. |

Examples:

```
{"source": "lid2005", "taxon": "Sorex minutus", "trait": "halelengde i forhold til kroppen", "value": "over 2/3 av kroppslengden", "qualifier": "always", "quote": "Halen er lang, over 2/3 av kroppslengden", "page": 412, "kind": "description"}
{"source": "lid2005", "taxon": "Sorex minutus", "trait": "vekt", "value": "3–6 g", "quote": "Vekt 3–6 g", "page": 412}
{"source": "lid2005", "taxon": "Sorex minutus", "trait": "bukfarge", "value": "hvit", "qualifier": "usually", "quote": "Buken er vanligvis hvit, sjelden grå", "page": 412}
{"source": "lid2005", "taxon": "Sorex minutus", "trait": "bukfarge", "value": "grå", "qualifier": "rarely", "quote": "Buken er vanligvis hvit, sjelden grå", "page": 412}
{"source": "lid2005", "taxon": "Sorex minutus", "trait": "snuteform", "value": "spiss, smal", "quote": "spiss snute", "page": "pl. 31", "kind": "figure"}
```

After `check_claims.py` the second line carries `"value_num": [3.0, 6.0], "unit": "g", "qualifier": "range"`.

## provenance.jsonl

Written by `digitize-clavis-key/scripts/score_claims.py`, and by hand for statements the digitizer adds in the generator. One line per statement.

| Field | Meaning |
|---|---|
| `statement` | The statement id in the key. |
| `claims` | Claim ids the statement rests on. Empty only with a `note`. |
| `note` | Why, when the mapping is not obvious. |

```
{"statement": "statement:3f9c…", "claims": ["claim:a1b2…", "claim:c3d4…"]}
```

## skipped.jsonl

One line per claim that deliberately did not become a statement.

| Field | Meaning |
|---|---|
| `claim` | The claim id. |
| `reason` | `not-observable`, `single-taxon` (only one taxon mentions the trait), `no-variation` (every taxon has the same value), `duplicate`, `out-of-scope`, `comparative-unresolved` (compares to something not in front of the user and no absolute reading exists), `other`. |
| `note` | Free text. |

```
{"claim": "claim:e5f6…", "reason": "single-taxon", "note": "Only S. minutus has a weight in this source"}
```

## Related tables

- `references/qualifiers.json`: per-language words that set `qualifier`.
- `references/frequency-table.json`: the one mapping from qualifier to statement frequency, used by `score_claims.py`. Frequencies are weak priors; any value above 0 keeps the taxon reachable.
