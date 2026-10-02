"""Taxonomy adapter for NorTaxa, the Norwegian taxonomy register, through the
Artsdatabanken Taxon API (https://artsdatabanken.no/Api/Taxon/...).

This is the reference adapter. To support another register, copy this file,
keep the three functions and SERVICE_ID, and change the lookups.
"""
import json
import time
import urllib.parse
import urllib.request

SERVICE_ID = "service:nortaxa"
BASE = "https://artsdatabanken.no/Api/Taxon"
SLEEP = 0.2  # be polite to the API between requests


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        j = json.load(r)
    time.sleep(SLEEP)
    return j


def _by_name(scientific_name):
    j = _get(f"{BASE}/ScientificName?scientificName={urllib.parse.quote(scientific_name)}")
    if isinstance(j, list):
        j = j[0] if j else {}
    return j or {}


def _by_id(taxon_id):
    return _get(f"{BASE}/{urllib.parse.quote(str(taxon_id))}") or {}


def resolve(scientific_name):
    rec = _by_name(scientific_name)
    hc = rec.get("higherClassification") or []
    accepted = rec.get("acceptedNameUsage") or rec.get("AcceptedNameUsage") or {}
    if not hc and accepted:
        hc = accepted.get("higherClassification") or []
    taxon_id = rec.get("taxonID") or accepted.get("taxonID")
    return {
        "taxonID": str(taxon_id) if taxon_id is not None else None,
        "higher": {h["taxonRank"].lower(): h["scientificName"]
                   for h in hc if h.get("taxonRank") and h.get("scientificName")},
    }


def vernacular(lang, taxon_id=None, scientific_name=None):
    if taxon_id is None and scientific_name:
        rec = _by_name(scientific_name)
        taxon_id = rec.get("taxonID") or (rec.get("AcceptedNameUsage") or {}).get("taxonID")
        if rec.get("vernacularNames") and taxon_id is None:
            return _pick(rec, lang)
    if taxon_id is None:
        return None
    return _pick(_by_id(taxon_id), lang)


def _pick(rec, lang):
    names = [v for v in (rec.get("vernacularNames") or [])
             if (v.get("language") or "").lower().startswith(lang.lower())]
    preferred = [v["vernacularName"] for v in names if v.get("nomenclaturalStatus") == "preferred"]
    if preferred:
        return preferred[0]
    if names:
        return names[0]["vernacularName"]
    p = rec.get("PreferredVernacularName")
    if lang == "nb" and isinstance(p, dict) and p.get("vernacularName"):
        return p["vernacularName"]
    return None
