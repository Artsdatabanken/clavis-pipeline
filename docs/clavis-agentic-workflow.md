# From books to a digital identification key: the Clavis agentic workflow

This document explains, from beginning to end, how one or more source documents (old books, field guides, websites, spreadsheets) are turned into a single, verified, digital identification key. It is written for readers with no background in biology, in identification keys, or in computing. Every technical term is explained the first time it appears.

## 1. What is an identification key?

Suppose you find a small mouse-like animal in your garden and want to know which species it is. An identification key is a tool that gets you to the answer through a series of observable questions: How long is the tail compared to the body? Are the ears visible above the fur? What color is the belly?

Each answer rules out some species. After enough answers, only one species remains - that is your identification.

Keys have been printed in books for centuries, usually as a numbered series of either/or choices ("1a: tail longer than body → go to 2; 1b: tail shorter than body → go to 5"). This classic form is called a dichotomous key, from the Greek for "cut in two." It works, but it is rigid: you must answer the questions in the book's order, and if you cannot answer one (the tail is missing, say), you are stuck.

A more flexible form is the matrix key. Instead of a fixed path of questions, it is a table: species are scored against questions. You answer whichever questions you can, in any order, and the software filters the list of candidates as you go. There is no wrong turn and no dead end. The table does not need to be complete: a question that is irrelevant or unknown for some species is simply left unscored for them, and the key still works. In practice the matrix is usually sparse, and that makes for a better key: the user is presented with a handful of relevant questions, rather than being overwhelmed with a long list.

## 2. What is Clavis?

Clavis is a digital file format for matrix keys, developed at the Norwegian Biodiversity Information Centre. A Clavis file is a structured text file (technically JSON, a common format computers read easily) containing four kinds of building blocks:

- Taxa: the things being identified - the species, arranged in their family tree (the plural of taxon, the general word for a named group of organisms such as a species, genus, or family).
- Characters: the questions - each about exactly one observable trait, such as "Tail length" or "Belly color."
- States: the possible answers to a character - for "Belly color" perhaps "White," "Gray," and "Brown."
- Statements: the actual scores - one entry per combination of taxon, character, and state, saying how often that species shows that answer.

That "how often" is a number between 0 and 1 called a frequency. A 1 means the species always shows this state, a 0 means never, and an in-between value means sometimes. Frequencies matter because a user holding an unusual individual must still be able to reach the right species: a state with frequency 0 is unreachable, so a possibility the source admits - however rare - is never set to 0.

Two structural rules of the format come up repeatedly below:

Statements can sit on a group instead of on each species. If a trait holds for every species in a family, it is recorded once on the family, and all species below inherit it. The flip side is a hard rule: a species may never restate a character its group already answers - the format has no concept of an exception or an override, and a double answer makes the file invalid. So a trait may only be recorded on a group if it holds for every member without exception; one deviant species means the trait must be recorded species by species instead.

There are no branches. Unlike the printed either/or key, a Clavis key has no fixed order; every character is an independent question. This has a practical consequence: the same trait may legitimately appear as two characters - for example a length in coarse steps for the whole key and the same length in finer steps that only distinguishes species within one group - and redundancy is a feature, because it gives the user multiple routes to the same answer.

## 3. What does "agentic" mean?

The work described here is done largely by AI agents. An agent is an AI system that is given a task, a set of written instructions, and access to tools (it can read files, run programs, look things up), and then works through the task step by step on its own, producing files as results.

The division of labor is fixed by design. Wherever a step can be done by an ordinary computer program - counting, checking, converting, comparing - a program does it, because programs are perfectly consistent and their results can be re-run. The AI is used only where judgment is needed: reading prose, deciding what a sentence in a 1990s field guide actually claims, or recognizing that two books describe the same trait in different words. Every such judgment is written down in a companion document so that a human expert can check and dispute it.

A second design choice: agents work in isolation. When several books are digitized, each book gets its own agent, and that agent never sees the other books. This keeps the resulting keys independent readings - one book's claims cannot contaminate another's - which matters later, at the merge, where agreement between sources is used as evidence.

## 4. The sources

A source does not have to be an identification key. Anything that carries information on how to recognize a species or tell it apart from its relatives qualifies: a ready-made key, but just as well plain prose descriptions of each species, a comparison table, measurements, illustrations with labeled details, or notes on behavior and habitat. A book chapter with no key in it at all - just a description of each species in turn - is a perfectly good source, because the workflow extracts distinguishing traits from whatever form the information takes.

The material can also arrive in essentially any physical or digital form:

- Scanned books, including historical ones from the National Library of Norway's online collection, which are downloaded page by page and then run through OCR (optical character recognition - software that turns a photograph of a page into machine-readable text).
- Modern PDFs of field guides and scientific monographs.
- Existing digital keys published on websites, which are read by small purpose-built programs called scrapers that extract the underlying data.
- Spreadsheets in which an expert has scored species against traits, converted by a small translation program.
- Existing Clavis files from other projects, which enter the pipeline as sources like any other.

Whatever the form, the goal of this stage is the same: get each source's relevant section into clean, readable text, with the page images kept at hand. The images matter because OCR handles flowing prose well but routinely drops or scrambles the floating labels around illustrations - the arrowed callouts on comparison plates ("note the pale wing patch") that often carry the densest identification information in the book. The agents therefore also look at the figures directly, with vision, and cross-check that every labeled feature ends up represented in the key.

## 5. The pipeline at a glance

1. Decide the scope: which species should the key cover?
2. Prepare each source: download, scan, OCR, scrape, or convert as needed, and cut out the relevant section.
3. Digitize: one independent agent per source turns that source into a draft Clavis key.
4. Audit: a fresh agent checks each draft against its source and fixes what it finds.
5. Merge: all audited keys are combined into one.
6. Verify and deliver.

The following sections describe what actually happens in each step.

## 6. Step 1 - Decide the scope

Before anything is read, the species list is fixed. For a Norwegian key it is built by a script from NorTaxa, the national taxonomy register (the authoritative database of which species occur in Norway and what their currently accepted scientific names are), supplemented with "doorknocker" species from the national alien-species assessments - species not yet established in Norway but considered likely to arrive. The list is saved as a small table and shown to a human before the pipeline continues, because scope is a decision a person should own.

This list is also the anchor for names. Scientific names change over time, and books use outdated ones. Every species name in every source is later resolved against the register, so that the same species appearing under different names in different sources becomes one entry. The matching is strict: only an exact match against an accepted name (or a documented synonym) is taken automatically. Fuzzy string matching is never trusted, because the names of two different species can differ by a couple of letters, and a wrong match would silently fold one species into another. An unresolvable name becomes a question for a human, not a guess.

## 7. Step 2 - Prepare each source

Each source is reduced once, up front, to exactly the section that matters: the pages covering the target group, extracted to a plain text file with a note recording the printed page offsets. The section boundaries are verified by reading the first and last pages of the candidate range, because stated page ranges are often slightly off, and text that looks relevant by keyword can turn out to be an index or glossary. If a species description spills onto a page outside the nominal range, the extraction is extended to include it.

This preparation serves accuracy and economy at once: the digitizing agent reads fourteen relevant pages instead of hunting through a three-hundred-page book, and the same extracted file later serves its auditor.

## 8. Step 3 - Digitize: one agent per source

The digitizing agent reads its entire section - every page, not just the printed key - and rebuilds the information as a Clavis key. The core of the work is a translation from prose to structure, and it follows explicit rules.

### Splitting sentences into single-trait characters

Book prose bundles traits. A step in a printed plant key that reads "stem hairy, leaves toothed, flowers yellow" makes three observations about three different parts of the plant, and becomes three characters, each with its own states. Splitting matters because a user may be able to answer one of the three and not the others; bundled into one question, the answer would be unusable for them. The agent keeps a running list of characters as it reads, and when the same trait comes up again later in the source - even deep in another part of the key - it is attached to the existing character rather than duplicated.

### Making the states a clean partition

The states of a character are the menu the user picks from, and they must form what mathematicians call a partition: every value the source claims must fall into exactly one state - never two, never none. The agent tests this in both directions, for every character, and records the result in a checklist table before the key file is generated.

Test one, no overlap: for every pair of states, is there any value that would satisfy both? A leg-count character with states "Six," "Eight or fewer," and "Many" fails, because an animal with six legs fits two states at once; the fix is to re-cut the states into "Six," "Seven to eight," "Nine or more." A color character with states "Brown," "Brown or gray," and "Black" also fails, because "Brown or gray" bundles two things an observer can tell apart; the fix is to split it, and to score any species the book calls variable across both resulting states.

Test two, no gap: for every claim in the source, does some state cover it? Suppose one plant species is described as having "5 or fewer stamens" and the others "exactly 8" or "exactly 10," and the drafted states are Four, Five, Eight, Ten. That fails: "5 or fewer" includes 3, 2, 1, and 0, and none of those values has a state. A user counting three stamens would have no answer to give, making that species unreachable for them. The fix is to add a state "Fewer than four" and score the bounded species across every state its claim spans.

Crucially, these tests are run against what the source asserts, interpreted only with ordinary language and arithmetic ("5 or fewer" includes 4, 3, 2, 1, 0). The agent is forbidden to use biological knowledge about what is "realistic" to shrink the space, because that is exactly how coverage gaps get papered over.

### Binning measurements

A character about a measurable quantity - a length, a weight, a count on a sliding scale - carries explicit numbers with units in its state labels: "under 40 mm / 40–60 mm / over 60 mm," not "small / medium / large," because two readers will disagree about where medium ends. This is a requirement wherever the source gives numbers to anchor with. When the source itself offers nothing better than relative wording, the information is still kept rather than thrown away - discarding it could cost the only thing separating two species - but the vagueness is flagged in the decisions document as a weak point for a better source to fix. Choosing the cut points is a judgment call: the agent places them where they best separate species, and documents the choice. When a species' true range crosses a cut point - the source gives a length of 35–45 mm and the boundary sits at 40 - the species is scored on both bins with paired frequencies, so a user measuring either side of the boundary still finds it.

### Scoring, inheritance, and honest uncertainty

For each species and each character, the agent writes the frequencies. The default shape is confident: one state at 1, the rest at 0. When the source admits more than one value - "usually brown, occasionally gray," "brown or gray," or a range crossing a bin boundary - the admitted states share the probability instead. Graded wording is kept graded: if the source says roughly one individual in twenty shows a trait, the encoding is 0.05, not a rounded 0.5, because the number carries information a user can exploit.

Before writing any statement, the agent asks whether the trait holds for every species of some larger group; if so, the statement goes on the group instead (this is called hoisting). One exception among the members means no hoisting - the trait is then scored member by member.

### Mining the descriptions

The printed key in a book typically uses a handful of traits, but the species descriptions around it mention many more: sizes, colors, habits, sounds, habitats, tracks. The agent walks these and applies a fixed decision rule for each trait it finds: add it as a character if at least two species mention it with different values (then it can actually separate species); skip it if only one species mentions it, or if every species that mentions it has the same value (then it separates nothing). Skipped traits are listed in the decisions document, so an expert can see the omissions were deliberate rather than oversights.

Two special cases have their own rules. Traits that cannot be observed on the specimen or find in front of you - how many offspring the species has per year, how long its development takes, how old it gets - do not become characters, because answering them requires already knowing the species. Geographic occurrence ("found in Norway: yes/no") may become a character, because it is genuinely useful, but the workflow tries hard not to let it be the only thing separating two species, since a user outside the assumed region cannot answer it. The audit later re-checks separability with the geography question removed; where a pair then becomes inseparable, the sources are searched for another separating trait, and if none exists the geography character is kept for that pair and the dependence is documented: those two species are separable only inside the region. That is a stated limitation of the sources, not something the workflow can conjure away.

### Ordering and labeling

The characters are ordered by how much access to the specimen each question requires: features visible at a glance first, then measurements, then habitat and behavior, then details that need the specimen in hand, and internal or microscopic features last. Labels follow fixed conventions - one measurement unit throughout the key, ratios always in percent, digits rather than number words, one capitalization style - so the finished key reads as one work rather than a patchwork.

### What the digitizing agent hands over

Rather than producing the key file directly, the agent writes a small generator program containing the species tree, the characters and states, and the scoring table; running the program produces the key file. This makes the work reproducible and cheap to fix: a corrected boundary is one edit in the generator, not a hunt through thousands of lines. Alongside the key, the agent delivers the decisions document (every judgment call, with reasons, written in the language of the source so its expert community can review it), the partition-test checklist, and a coverage note listing which species from the project list the source covers and which it lacks.

## 9. Step 4 - Audit: fresh eyes on every draft

Every draft is audited before it may enter the merge - by a different agent that has not seen the digitizing work and has nothing to defend. The audit runs in five phases, in order.

Phase 1 is a deterministic verification program. It checks, mechanically: the file parses; every statement points to a species, character, and state that actually exist; no state is used with the wrong character; every frequency lies between 0 and 1; every answered species-character combination leaves at least one state reachable; no character is stated both on a group and on one of its members; and no two species have ended up with identical answers to every question. That last flag usually means an encoding mistake, for example a trait hoisted onto a group when the two species actually differ in it. But if the source genuinely offers no way to separate the pair, that is a legitimate limitation of the source, recorded as such rather than papered over.

Phase 1b runs cheap convention checks: a program parses every numeric state label and reports gaps and overlaps between bins ("20–50 mm" followed by "over 100 mm" strands every value in between); labels are scanned for mixed units and inconsistent notation; and the auditor lists non-committal scores - species given a nonzero frequency on every state of a character. Such a score is a real score and can be correct (the species genuinely spans all values), but that question can then never rule the species out, so the listing is a diagnostic: it separates the healthy case, where a question that cannot exclude one species still narrows down the others, from the suspect one, where a character is non-committal for most species and probably cannot really be answered at all, making it a candidate for removal.

Phase 2 redoes the two partition tests from scratch, for every pair of states in every character. Beyond the overlap types described earlier, the auditor looks specifically for a subtle third kind: states from different trait axes mixed into one character - "green" sitting next to "with two prominent spots" as answers to the same question. A specimen can be both at once, so the user cannot pick one answer; the fix is to split the character itself into a color character and a pattern character, redistributing every score.

Phase 3 checks that every character about a measurable quantity has numeric ranges on all its states, and asks whether the numbers would be better stored as actual measurements than as bins where the format allows it.

Phase 4 is the source-coverage spot check: the auditor picks a sample of species, re-reads their descriptions in the source sentence by sentence, looks at the figures with vision, and verifies that each observable feature the source mentions is captured somewhere in the key. Anything missing is either added (if it passes the two-species-different-values rule) or logged as deliberately skipped. This phase also re-runs the separability check with the geographic-occurrence character removed, to prove no species pair depends on geography alone.

Phase 5 applies all fixes and re-runs Phase 1 until it passes. The corrected key is saved as a new version alongside the original - nothing is overwritten - together with an audit-findings document listing what was found and what was done about it.

## 10. Step 5 - Merge: many keys become one

The audited keys, one per source, are now combined. The merge is a sequence of defined operations, each producing an intermediate file and a short report, so any stage can be redone.

### Union first

All keys are stacked into one big union: every source's species, characters, and statements, side by side, with each item tagged by its source. Nothing is reconciled yet. The reason for this ordering is fairness: a union has no order, so no source counts more than another. Merging keys one at a time would quietly weight the last source heaviest.

Any source that encoded a printed key's steps verbatim - states that are whole multi-clause sentences - is first decomposed into single-trait characters, exactly as the digitizing rules require, because a bundled sentence cannot be matched against a clean trait.

### Matching species and characters

Species are matched by their resolved accepted names from Step 1: same accepted name, same species. Each species now simply carries all its sources' scores next to each other.

Characters are matched by building a concordance: a table saying which characters from different sources describe the same observable trait. The matching criterion is meaning - what would the user actually look at? - decided by reading the character titles and states. Statistical agreement of the underlying data (do the sources score the species the same way?) is used only as supporting evidence when the meaning is uncertain, never as the trigger, because with few species, two completely unrelated traits can agree perfectly by chance. Measurement bins are matched by computing the numeric overlap of the parsed ranges, never by eye, because hand-copied boundaries are where transcription errors hide.

### Reconciling the scores

For each merged character, every source's states are mapped onto one agreed set of states, and then, species by species, the sources' claims are combined:

- If the sources' claims overlap, the answer is the intersection - the most precise claim wins. One source gives a measurement, "45–60 mm"; another only says "long": the measurement stands, and the vague claim is recorded as narrowed, not lost.
- If the claims do not overlap at all, that is first treated as a symptom, not a finding. Most apparent conflicts turn out to be errors in the merge's own mapping tables, such as two of a source's states accidentally swapped during reconciliation, so the mapping is re-examined before the sources are declared to disagree. Only a conflict that survives this scrutiny counts as real disagreement.
- A real disagreement is preserved, not voted away. Each source gets one vote, split evenly across the values it allows, and the frequencies are the normalized sums - so every value any source asserts remains reachable, weighted by how many sources back it. Majority rule is deliberately not used: dropping the minority claim would silently destroy source information, and the round-trip check at the end would catch exactly that.
- When two states are merged into one, a species' frequencies on them are added (the states were mutually exclusive alternatives), then rescaled if the total exceeds 1. Graded values are carried through untouched.

### Hierarchy and cleanup

The family-tree structure of the merged key comes from the national register, never from the sources (which disagree about classification), and its depth is decided by a counting rule rather than taste: with 16 or fewer species, a flat list under the root is used; above that, a rank (family, genus, and so on) qualifies if every species has an ancestor at that rank and it yields between 2 and half-the-species-count groups, and the deepest qualifying rank is kept. For example, 29 species falling into 6 families but 18 genera get grouped by family: 18 groups for 29 species would fragment the list rather than organize it. Vernacular names are fetched from the register by ID; missing ones stay empty rather than being invented.

Cleanup then applies the field-usability tests from digitization to the union as a whole: characters no user could answer on an encounter are removed, geographic characters are stripped back to the species pairs that genuinely need them, and true duplicates created by the couplet-splitting are folded together. Every removal is logged with its cost.

Finally, the union's vocabulary is coarsened. Stacking all sources yields the finest wording of each - "gray" beside "slate gray," five named shades of brown - which is precise on paper and unanswerable with a specimen in hand. Candidate merges of neighboring states are proposed semantically but accepted or rejected by measurement, against three criteria: no species pair may lose its last separating character; no pair that had three or more independent ways to be separated may drop below three; and the character itself must keep at least three quarters of its own separating power, so the process cannot hollow a question out while overall redundancy hides the damage. Merges are applied greedily, best first, re-measuring after each.

## 11. Step 6 - Verify and deliver

The merged key must pass all of the following, in order:

- The deterministic verification program from the audit, again, on the final file.
- The bin-continuity check: every numeric answer scale gapless and overlap-free.
- The round-trip check: every positive claim from every source is replayed against the finished key, through the accumulated mapping tables (name aliases, character concordance, every state rename and coarsening). Each claim must come back as survived (some asserted value still reachable), narrowed (superseded by a more precise source), or deliberately removed (on the documented list). Zero silent losses; if any claim comes back unaccounted for, something upstream is wrong and gets fixed. The mapping tables must be kept current through every late change, because a stale checker either reports false losses or, worse, skips renamed items while appearing to pass.
- The redundancy report: for every pair of species, the number of independent characters that can separate them. Pairs no source can separate are documented as limitations of the source material, distinguished from anything the merge itself caused.
- The geography check: every pair separable only by occurrence has been either given another separator or documented as region-bound.
- Two-way coverage against the species list: which listed species the key misses (and which kind of additional source would fix that), and which species the sources cover beyond the list.

The deliverables are the key file and its companion documents - the decisions record for the merge, the updated partition-test tables, the audit findings, the removed-characters list, the round-trip report, and the coverage and redundancy reports - written in the key's language and converted to PDF at the end. The companions exist so that the finished key is not a black box: each choice made between the source pages and the final file is recorded with its reasoning, and each can be disputed by an expert without rerunning anything.
