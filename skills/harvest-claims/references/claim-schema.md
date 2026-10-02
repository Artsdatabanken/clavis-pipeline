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
| `qualifier` | harvester | `always`, `usually`, `sometimes`, `rarely`, `range`, `comparative`. The harvester reads the source's wording and sets it; the checker only notes when it is missing. |
| `values` | harvester | When the source lists alternatives for one trait ("brown or grey", "svart til gråbrun"): the list of values, one per alternative, with `value` holding the wording as written. The scorer matches each entry. |
| `quote` | harvester | The verbatim passage or figure label the claim rests on. |
| `page` | harvester | Printed page number, or plate/figure id. |
| `kind` | harvester | `description`, `key`, `table`, `figure`. Default `description`. |
| `observable` | harvester | `false` for traits that cannot be seen on a specimen or find. Default `true`. |
| `value_num` | harvester (the checker fills it only for symbol forms like `3–6 g`, `< 30 mm`) | `[min, max]`; `null` on an open side (`over 24 mm` → `[24, null]`, `opptil 2,5 cm` → `[null, 2.5]`). The checker verifies each number occurs in `value` or `quote`. |
| `unit` | harvester | Unit as written in the source (`mm`, `g`, `%`). |
| `diagnostic` | harvester (claims of kind `key` default to true) | `true` when the source presents the trait as what distinguishes the taxon (a key couplet, "recognized by", "differs from X in"). The digitizer scores the other taxa absent on that character. |
| `absent_for` | harvester | For a claim from a key couplet: the taxa under the opposite lead of that couplet. The digitizer scores the trait absent for exactly those taxa, not for every taxon in the source. |
| `same_as` | harvester | Scientific name of a taxon this one cannot be told from, per the source ("ingen ytre forskjeller fra ..."). The digitizer copies that taxon's values where this one has none. `trait` and `value` describe the statement itself. |
| `note` | `check_claims.py` | Something the harvester must fix: a missing qualifier, a number in `value_num` that is not in the quote, a missing unit. |

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

- `references/frequency-table.json`: the one mapping from qualifier to statement frequency, used by `score_claims.py`. Frequencies are weak priors; any value above 0 keeps the taxon reachable.
