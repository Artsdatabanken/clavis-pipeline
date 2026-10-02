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
2. Prepare each source once: text, each species' pages, the figures.
3. Harvest: one agent per source lists, species by species, every claim the source makes, with a quote and a page.
4. Digitize: one agent per source designs the key's questions from the claims; a program scores the answers.
5. Audit: a fresh agent checks each draft against the claims and fixes what it finds.
6. Merge: all audited keys are combined into one.
7. Determinability: a fresh agent makes every answer something a person can pick with one specimen in hand.
8. Gates: a program measures the result; the run is finished only when every gate passes, and the cost is reported.

The following sections describe what actually happens in each step.

## 6. Step 1 - Decide the scope

Before anything is read, the species list is fixed. For a Norwegian key it is built by a script from NorTaxa, the national taxonomy register (the authoritative database of which species occur in Norway and what their currently accepted scientific names are), supplemented with "doorknocker" species from the national alien-species assessments - species not yet established in Norway but considered likely to arrive. The list is saved as a small table and shown to a human before the pipeline continues, because scope is a decision a person should own.

This list is also the anchor for names. Scientific names change over time, and books use outdated ones. Every species name in every source is later resolved against the register, so that the same species appearing under different names in different sources becomes one entry. The matching is strict: only an exact match against an accepted name (or a documented synonym) is taken automatically. Fuzzy string matching is never trusted, because the names of two different species can differ by a couple of letters, and a wrong match would silently fold one species into another. An unresolvable name becomes a question for a human, not a guess.

## 7. Step 2 - Prepare each source

Each source is reduced once, up front, by programs rather than by an agent reading the book:

- The text layer is extracted once (`pdftotext`; a scanned book is OCR'd first, and the OCR step also records where the figures are on each page).
- The species list, extended with vernacular names from the register, is searched in the text. The pages where each species is treated, the page range of the whole section and the offset between printed and PDF page numbers come out of that search. A person confirms only the first and last page of the section.
- Every figure, plate and table in the section is listed with its page and, where known, its position on the page, and cut out as a small image.

The result is one small text file per species and a folder of figure crops. Nobody downstream reads the whole book, or whole page images, by default. This is where most of the cost of the earlier runs went: a 300-page book re-read by ten agents.

## 8. Step 3 - Harvest: one agent per source, species by species

A harvester gets one source: a small text file per species and the figure crops, and nothing else. It works through the species one at a time, with only that species' file open. (The first run used one agent per species; the fixed cost of starting an agent, multiplied by a hundred, was most of the bill, so one agent per source it is.) It writes one line per claim the source makes about that species: the trait ("tail length relative to body"), the value as the source gives it ("over 2/3 of body length", "3–6 g"), how often the source says it holds (always, usually, rarely), the verbatim quote, and the printed page. Bundled sentences become several claims. Figure labels become claims. Traits that cannot be observed on a specimen (litter size, lifespan) are recorded too, marked as such, so that later steps can prove they were seen and deliberately left out. Two more things are marked: a trait the source presents as what distinguishes the species (a step in the printed key, "recognized by"), and a statement that the species cannot be told from another one ("no external differences from the common vole").

A program then checks every line, parses the numbers and units ("3–6 g" becomes the range 3 to 6, unit grams), fills in the frequency word from the quote where the harvester left it open, removes duplicates and gives each claim a stable identifier. The harvester never designs anything and never judges what matters. That is the point: a list of what the book says, line by line, with a page number on each, is hard to argue with and easy to check against the page.

## 9. Step 4 - Digitize: one agent per source, from the claims

The digitizing agent does not read the book. It reads the claims file, groups the claims by trait, and decides for each trait: does it become a question in the key, or is it skipped, and why? Every claim ends up in exactly one of those two places, and the program at the end proves it.

For each question the agent writes a design, not the answers:

### Single-trait questions with answerable states

A question is about one observable trait. Its possible answers, the states, must be a clean partition of everything the source asserts: every asserted value falls into exactly one state, never two, never none. "Brown or grey" is never a state; it is two statements. The states must also be answerable by one person with one specimen and the guide, without another specimen to compare against and without experience: "darker than the field vole" is not an answer a user can give; "grey-brown" is.

### Measurements stay numbers

A trait the source gives numbers for - a length, a weight, a count on a scale, a ratio - becomes a numerical question. Each species gets its range, the union of what the source says for it, with a unit. There are no bins and no cut points to choose: the viewer compares the user's measurement with the ranges. Earlier versions of this pipeline binned measurements ("under 40 mm / 40–60 mm / over 60 mm") and spent much effort choosing and auditing cut points; a format that stores ranges needs none of that.

### Frequencies are weak priors

For each claim, a program writes the statement in the key and the number that says how often the species shows that value. The number comes from one fixed table: always 1, usually 0.9, sometimes 0.4, rarely 0.1. Its only hard meaning is that zero excludes a species and anything above zero keeps it reachable. A rare form must still lead to the right species, and a 0.1 is enough for that; nothing in the pipeline argues about 0.8 versus 0.7, and sources are never made to vote on a number. Where a species shows exactly one of several states, nothing is written for the others: zero is implied, which keeps the files small.

### What the source implies

Two rules turn the book's own logic into statements, by program, never by invention. A trait the source presents as diagnostic for one species is, by that logic, absent in the other species the source describes: the beaver's flat tail is scored "flat" for the beaver and "not flat" for every other species, each pointing at the same quoted passage. And a species the source says cannot be told from another one gets that one's values for every trait the source does not state for it, again pointing at the quote; the two species then differ only where the sources differ, which is what the books said. Without these rules a key loses exactly the characters a field guide considers most useful.

### Provenance

Every statement in the key records the claims it rests on, and every claim the agent decided to skip is listed with its reason. These two lists are what the audit and the final gate measure: every statement traces to a quoted passage, and every passage reached the key or was deliberately left out.

### What the digitizing agent hands over

The design file, the scored key produced by the program, the provenance and skipped lists, and a decisions document in the language of the source: which trait wordings were folded into one question, which comparatives were rewritten into absolute terms or dropped, where the source contradicts itself and which reading was trusted. Species are a flat list; the family tree comes later, from the register.

## 10. Step 5 - Audit: fresh eyes on every draft

Every draft is audited before it may enter the merge - by a different agent that has not seen the digitizing work and has nothing to defend. The audit works from the claims and their quotes, not from the book.

First the programs: the structural verifier (the file parses; every statement points to a species, question and answer that exist; frequencies lie between 0 and 1; a species' range lies inside the question's range; no question is stated both on a group and on one of its members; no two species end up with identical answers to everything); the claims audit in both directions; the range check; and the coverage test, which lists every claim whose wording does not match the state it was mapped to, so that the auditor looks only at the mappings that needed judgment.

One more program checks the claims against the book itself, the step no other check covers: every quote must occur word for word in the source, and every stretch of eight or more words on the harvester's pages that no claim quotes is listed. The auditor, who is not the harvester, reads each stretch and either adds the claims that were missed or records why there are none (not about a listed species, nothing observable, unreadable). The share of the book's words that ended up quoted is reported.

Then the judgment, on the flagged rows only: do sibling states overlap; is a measurement hiding as a set of bins; is a state a fair reading of its quote ("small round ears" scored as "ears clearly protruding" is not); can a user pick each state with one specimen in hand. Then the fixes, applied through the design so the program reproduces the key, and the programs again, until every count is zero. The corrected key is saved as a new version alongside the original - nothing is overwritten - together with a findings document.

## 11. Step 6 - Merge: many keys become one

The audited keys, one per source, are now combined. The merge is a sequence of defined operations, each producing an intermediate file and a short report, so any stage can be redone.

### Union first

All keys are stacked into one big union: every source's species, questions, and statements, side by side, with each item tagged by its source. Nothing is reconciled yet. The reason for this ordering is fairness: a union has no order, so no source counts more than another. Merging keys one at a time would quietly weight the last source heaviest.

### Matching species and questions

Species are matched by their resolved accepted names: same accepted name, same species.

Questions are matched by a concordance: which questions from different sources describe the same observable trait. A program proposes candidate pairs (similar titles, a glossary of known synonyms across languages, shared answer labels, overlapping measurement ranges), and the agent decides by meaning - what would the user actually look at? - and writes one specification file: for each merged question its type, its answer labels, and for every source question that feeds it how each source label maps onto the merged labels. The maps are kept per source question, because "yes" means different things in different questions.

### Reconciling the answers

For each merged question, species by species, the sources' claims are combined by a program:

- Measurements: the merged range is the union of the sources' ranges, lowest minimum to highest maximum. Nothing is averaged and nothing is voted on.
- Single-choice questions: if the sources' sets of allowed answers overlap, the overlap is the answer - the most precise source wins, the vague one is narrowed, not lost. If they do not overlap at all, that is first treated as a symptom: most apparent conflicts are errors in the mapping file, and those are fixed before anything is called a disagreement. A real disagreement keeps every asserted value reachable; the number attached to each is the highest any source gave it.
- Multiple-choice questions (habitats, signs): every asserted answer is kept with its own number; nothing is intersected.

### Hierarchy, location and determinability

The family-tree structure of the merged key comes from the national register, never from the sources (which disagree about classification), and its depth is decided by a counting rule rather than taste: with 16 or fewer species, a flat list; above that, the deepest rank at which every species has an ancestor and which yields between 2 and half-the-species-count groups. Traits that every species under a node shares are moved up to that node by a program that aborts unless every species' effective answers are unchanged. Vernacular names come from the register.

Location questions ("occurs in Norway") are a last resort: a program measures, for each species pair, whether the pair would lose its last separating question, or drop below three, without them; the location question is kept only for the species that need it, stripped from the others, and dropped entirely when no pair needs it. Every removal is logged so the round-trip can account for it.

Then a fresh agent runs the determinability pass on the merged key: a program flags every answer that compares to something not in front of the user, every bundle, every size word without a number, and every question with more shades than a person can name; the agent decides only the flagged rows. Shades are merged through a measured coarsening: a merge is accepted only if no species pair loses its last separating question, no pair that had three or more drops below three, and the question keeps three quarters of its own separating power. Comparatives are rewritten in absolute terms or removed; bundles are split; any leftover bins become a numerical question.

## 12. Step 7 - The gates, and the cost

One program runs every gate on the final key and writes one table. The run is finished only when every required gate passes:

- The structural verifier, again, on the final file.
- The range check: every numerical question has a unit and valid ranges.
- The claims audit per source: zero statements without a claim, zero claims unaccounted for.
- The round-trip: every positive claim of every source is replayed against the finished key through the same specification and rename files the merge used. Each must come back as survived (some asserted value still reachable; for multiple-choice questions every asserted value; for measurements the merged range contains the source's), narrowed (superseded by a more precise source), or deliberately removed (on the logged list). Zero silent losses; a stale rename chain is the classic false loss, so the checker reads the merge's own files.
- The redundancy report: for every pair of species, the number of independent questions that separate them (two measurement ranges separate when they do not overlap). Pairs no source separates are documented as limits of the source material.
- The geography check: no pair separable only by location.
- Two-way coverage against the species list.
- Tokens and cost: every model call of the run, orchestrator and agents, summed from the harness's logs and priced, with the wall-clock time.

A failed gate is work, not a result: the cause is fixed where it lives and every gate runs again. The deliverables are the key file and its companion documents - the gate table, the decisions record, the round-trip, redundancy, removed-questions and coverage reports, the cost report - written in the key's language. The companions exist so that the finished key is not a black box: each choice made between the source pages and the final file is recorded with its reasoning, and each can be disputed by an expert without rerunning anything.

## 13. Which models, and what it costs

The recommended setup is one capable model (Claude Opus 5.5) running the job and a mid-size model (Claude Sonnet 5.5) doing every agent's work. The model running the job is where the judgment calls are: which pages belong to the group, whether a harvester's "cannot be told apart" is really what the book says, what to do when a script breaks on real data. The agents follow written procedures with programs behind them.

On a key to 24 species built from five printed field guides and one existing digital matrix key, that setup took 73 minutes and about 172 million tokens of input read from cache and 7 million written to cache, across 21 agents. At Claude API list prices on 2 October 2026 that is about 56 US dollars; on a subscription plan the practical cost per run is a few dollars. Almost all of it is input: every model call re-reads its agent's context. That is why the pipeline gives every agent the smallest files that do the job (one species' pages, the figure crops, the claims instead of the book) and pushes every step that can be measured into a program.

The aim is to make good keys from as little computation as possible. Anyone who runs the pipeline with another model, a local one included, is asked to report how it went, with the same numbers, so that the smallest setup that still produces a good key can be found.
