# Adapters

Everything in the pipeline that talks to a particular register or national service lives here. The skills and merge scripts call these; they never call a service directly.

- `taxonomy/`: resolve a scientific name, get its higher classification, get a vernacular name. One module per register; `nortaxa.py` is the reference implementation and the default. See `taxonomy/__init__.py` for the three-function contract.
- `species-list/`: build the species CSV that scopes a key. `norway.py` combines NorTaxa with the Norwegian alien-species list. Another region needs a script that writes the same columns: `scientificName,inNorway,doorknockerRisk` (rename the second column to your region; the pipeline only reads `scientificName`).

The vernacular-name adapter for translation stays inside `skills/translate-json/pipeline/adapters/`, because that skill runs it as a Python module from its own folder. It cascades NBIC, SLU Artdatabanken, GBIF, Wikispecies and iNaturalist and is already register-agnostic in its output.

Select a taxonomy adapter with `CLAVIS_TAXONOMY=<name>` or `--taxonomy <name>` on the merge scripts.
