# Phase 2: sibling-state disjointness and coverage

Part of the `audit-clavis-key` skill. Read when SKILL.md points here.

### Phase 2: Sibling-state disjointness audit

This phase enforces Protocol 1 from `digitize-clavis-key`. The protocol requires the state set of each character to **partition** the source-asserted values: every asserted value falls into exactly one state — never two (overlap), never zero (coverage gap). Both directions are checked, both produce required output.

**Key framing.** The state space derives from what the source claims, plus basic linguistic and mathematical reasoning about what those claims include. *E.g.* "5 or fewer" includes 4, 3, 2, 1, 0; "longer than 10 cm" includes 11, 12, …; "either red or yellow" includes both red and yellow. Do **not** invoke domain knowledge about what's "plausible" or "biologically reasonable" — that smuggles in unverifiable assumptions and is the exact mechanism that hides coverage gaps.

#### Test A — sibling-state disjointness

For every pair of sibling states *(A, B)* inside one character, ask:

> *Is there any value the source asserts that satisfies both predicate A and predicate B?*

If yes for any pair, overlap, fix.

**Three** distinct kinds of overlap, all real violations — none of them are "borderline":

- A state whose values are a strict superset of another's (e.g., a numeric range that contains another, or a quantifier like *"five or fewer"* alongside *"four"*) overlaps. Fix by re-binning into a true partition.
- A state combining distinguishable values (any phrasing where the source admits two observably different things in one bin) overlaps with whichever splits exist or should exist. Fix by splitting.
- **Cross-axis overlap**: states that describe different observable axes mixed in one character (e.g. *"groen"* sitting next to *"met twee prominente vlekken"*, or *"breder dan lang"* sitting next to *"dakvormig"*). A specimen can satisfy one state on each axis simultaneously, so any sibling pair drawn from different axes overlaps under Test A. **The character itself is bundled** — fix by splitting the character into one new character per axis (Phase 5 fix). Don't dismiss as "borderline" or "different information level" — Test A says it's an overlap, the user can't pick "the" state, and the key is unusable as-is.
- A state defined relatively (*small*, *long*, *thick*) without numeric anchors implicitly overlaps all sibling relative-anchor states. Defer to Phase 3 — it requires anchors.

Heuristic for triage (not the rule): scan state labels for logical-disjunction connectors in the file's language(s), or for the cross-axis pattern — modifier prefixes (*met / with / mit / med / avec*) sitting next to bare terms in the same character. Either pattern triggers the test; the test decides.

#### Test B — coverage of source-asserted values

Walk every assertion the source makes about each trait. For each value asserted (a specific count, a measured length, a stated range, or a bound like *"X or fewer" / "more than X" / "between X and Y"*), ask:

> *Does at least one state cover this asserted value?*

If no for any source-asserted value, coverage gap, fix.

The most common coverage gap: a one-sided bound assertion. *Example:* one taxon described as *"5 or fewer stamens"* and others as *"exactly 8"* or *"exactly 10"*. A state set of *Four / Five / Eight / Ten* fails coverage — values 0, 1, 2, 3 are admitted by *"5 or fewer"* but no state covers them. Fix: add a state *Fewer than four*. The bounded taxon is then encoded as paired uncertain frequencies across every state its bound spans (here, *Fewer than four* + *Four* + *Five*).

The same applies to upper-bound assertions, range assertions whose endpoints fall outside a discretization, and enumerated value lists where one of the listed values has no state.

**Coverage-gap is exactly as serious as overlap.** A taxon at the unbounded end of a one-sided bound is unreachable for the user observing that end. The audit phase catches this only because the digitize phase failed to apply Test B; both skills are responsible.

#### Required output

Produce or update the audit table at `<output>.character-audit.md`:

| Character | Sibling pair / source-asserted value | Test | Verdict | Fix (if violation) |
|---|---|---|---|---|
| Coat colour | Brown vs Brown-or-grey | A (disjointness) | ❌ | Split *Brown-or-grey* into atomic *Grey*; re-encode taxa with paired 0.5/0.5 |
| Number of legs | Six vs Eight-or-fewer | A | ❌ | Re-bin into *Six / Seven–eight / Nine or more* |
| Number of legs | Six vs Many | A | ✅ | — |
| Number of stamens | Source asserts "5 or fewer" (covers 0-5) | B (coverage) | ❌ | Add state *Fewer than four*; pair 0.5/0.5/0.5 across *<4*, *4*, *5* for that taxon |
| Number of stamens | Source asserts "exactly 10" | B | ✅ | — |

Every sibling-pair row and every distinct source-assertion row must appear. The table is the audit's primary output.
