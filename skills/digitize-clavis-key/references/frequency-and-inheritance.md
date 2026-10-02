# Frequencies and inheritance

Part of the `digitize-clavis-key` skill. Read when SKILL.md points here.

## Frequencies are weak priors

`frequency` is any number from 0 to 1. The only hard meaning: **0 excludes the taxon** for that value, **anything above 0 keeps it reachable**. The size of the number is a prior the viewer can rank with; it is not data the source gave, and nothing downstream should treat 0.9 versus 0.7 as information worth arguing about.

So frequencies come from one fixed table, `harvest-claims/references/frequency-table.json`, applied by `score_claims.py` from the claim's qualifier:

| qualifier | frequency | alternative value in the same claim |
|---|---|---|
| always, range, comparative, unspecified | 1 | |
| usually | 0.9 | 0.3 |
| sometimes | 0.4 | 0.6 |
| rarely | 0.1 | 1 |

No voting between sources, no averaging, no prose about why a value is 0.8. Change the table once if you want different priors.

Rules that follow:

- **Never exclude a value the source admits.** "Usually white, rarely grey" gives white 0.9 and grey 0.1; a user with the rare form still reaches the taxon. A state at 0 is unreachable.
- **Exclusive characters carry no zero statements.** Zero is implied for every sibling state the taxon has no statement on. This is what keeps keys small; the viewer and `verify.py` both read it that way.
- **Non-exclusive characters** get one statement per asserted state, each with its own frequency; absent states say nothing.
- **Numerical characters** have one statement per taxon, frequency 1, value `[min, max]`.
- **Rounding:** 1 is written as `1`, never `0.9999`.

## Inheritance: the merge does it

A statement on an ancestor holds for every descendant, and a descendant may never restate the same character (no overriding; `verify.py` rejects it). Per-source keys from this skill have a **flat taxon list** and no hoisting: the merge builds the hierarchy from the taxonomy register and hoists what every leaf under a node shares. Do not build a tree from the source's chapter structure.
