"""Taxonomy adapters: one module per register, all with the same three functions.

Every adapter module provides:

    SERVICE_ID: str
        The Clavis externalServices id written into externalReference,
        e.g. "service:nortaxa".

    resolve(scientific_name) -> {"taxonID": str | None, "higher": {rank: name}}
        Look a scientific name up. "higher" maps lowercase rank names
        ("family", "genus", ...) to the ancestor's scientific name. Returns
        taxonID None and an empty dict when the name is unknown. Must use exact
        accepted-name matching (or a documented synonym); never fuzzy matching.

    vernacular(lang, taxon_id=None, scientific_name=None) -> str | None
        Preferred common name in `lang` (ISO 639-1), by id when given,
        otherwise by name. None when the register has none.

Adapters may sleep between requests and may raise on network errors; the
callers cache results and report failures per taxon.

Select an adapter with load("nortaxa") or the CLAVIS_TAXONOMY environment
variable. Scripts default to "nortaxa".
"""
import importlib
import os


def load(name=None):
    name = name or os.environ.get("CLAVIS_TAXONOMY") or "nortaxa"
    return importlib.import_module(f"{__name__}.{name}")
