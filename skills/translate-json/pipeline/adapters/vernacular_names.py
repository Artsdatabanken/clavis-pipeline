"""Resolve vernacular names from authoritative sources before falling back to a model.

Ported from taxon.js. Cascades through:

  1. NBIC (Artsdatabanken) — by scientificNameId if available, else by scientificName.
     Returns RecommendedVernacularName_<lang> entries for many languages.
  2. Artdatabanken Sweden — only for target=sv, requires ARTDATABANKEN_TOKEN.
  3. GBIF — Catalogue of Life dataset, vernacularNames with 3-letter codes.
  4. Wikispecies — interwiki language links; cleaned page titles in target language.
  5. iNaturalist — autocomplete with locale=<target>.

Stops at the first source that returns a non-empty target string. Caches per
(scientificName, target_lang). Works for any ISO 639-1 target language; some
sources support more languages than others.

Usage:
    python -m pipeline.adapters.vernacular_names STRINGS.jsonl \\
        --target en --out-resolved RESOLVED.jsonl --out-remainder REMAINDER.jsonl \\
        [--cache adapter_cache.json] [--sleep 0.1]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "translation-pipeline/0.1 (+https://github.com/WouterKoch/Clavis)"
TIMEOUT_S = 5

# GBIF 3-letter -> 2-letter
GBIF_LANG_MAP = {
    "swe": "sv", "eng": "en", "nld": "nl", "spa": "es",
    "deu": "de", "fra": "fr", "ita": "it", "por": "pt",
    "fin": "fi", "dan": "da", "nob": "nb", "nno": "nn",
    "isl": "is", "pol": "pl", "rus": "ru", "ces": "cs",
    "ell": "el", "hun": "hu", "ron": "ro", "tur": "tr",
    "ukr": "uk", "jpn": "ja", "zho": "zh", "kor": "ko",
}
GBIF_INV = {v: k for k, v in GBIF_LANG_MAP.items()}


def _http_get_json(url: str, *, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "identity",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clean(name: str | None) -> str | None:
    if not name:
        return None
    s = name.strip()
    return s or None


# ---------- NBIC ----------

def nbic_by_sci_name_id(sci_name_id: str, target: str) -> tuple[str | None, str]:
    """Return (vernacular, source_note). Looks up resource for the taxon and pulls RecommendedVernacularName_<lang>."""
    try:
        sci_obj = _http_get_json(
            f"https://artsdatabanken.no/Api/Taxon/ScientificName/{urllib.parse.quote(sci_name_id)}"
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "nbic_sciname_lookup_failed"
    taxon_id = sci_obj.get("taxonID")
    if not taxon_id:
        return None, "nbic_no_taxonid"
    try:
        resource = _http_get_json(
            f"https://artsdatabanken.no/Api/Resource/Taxon/{urllib.parse.quote(str(taxon_id))}"
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "nbic_resource_lookup_failed"
    return _extract_nbic_vernacular(resource, target)


def nbic_by_sci_name(sci_name: str, target: str) -> tuple[str | None, str]:
    try:
        # Capped search; we accept any AcceptedNameUsage hit on the exact name.
        params = urllib.parse.urlencode({"Take": "50", "Type": "taxon", "Name": sci_name})
        results = _http_get_json(f"https://artsdatabanken.no/api/Resource/?{params}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "nbic_resource_search_failed"
    if not isinstance(results, list):
        return None, "nbic_unexpected_shape"
    for t in results:
        name = (t or {}).get("Name") or []
        if not isinstance(name, list):
            name = [name]
        if any(sci_name in (n or "") for n in name) and t.get("AcceptedNameUsage"):
            return _extract_nbic_vernacular(t, target)
    return None, "nbic_no_match"


def _extract_nbic_vernacular(resource: dict, target: str) -> tuple[str | None, str]:
    # The NBIC resource dict carries RecommendedVernacularName_<lang> properties at the top level.
    candidates: list[str] = []
    for k, v in (resource or {}).items():
        if isinstance(k, str) and k.startswith("RecommendedVernacularName_") and v:
            lang = k[len("RecommendedVernacularName_"):].split("-")[0].lower()
            if lang == target.lower():
                candidates.append(v)
    if candidates:
        return _clean(candidates[0]), "nbic"
    return None, "nbic_no_target_lang"


# ---------- Sweden Artdatabanken (sv only, auth) ----------

def sweden_artdatabanken(sci_name: str) -> tuple[str | None, str]:
    token = os.environ.get("ARTDATABANKEN_TOKEN")
    if not token:
        return None, "sweden_no_token"
    params = urllib.parse.urlencode({
        "searchString": sci_name,
        "searchFields": "Scientific",
        "isRecommended": "Yes",
        "culture": "sv_SE",
        "page": "1",
    })
    try:
        data = _http_get_json(
            f"https://api.artdatabanken.se/taxonservice/v1/taxa/names?{params}",
            headers={"Ocp-Apim-Subscription-Key": token},
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "sweden_lookup_failed"
    items = (data or {}).get("data") or []
    for item in items:
        if (item.get("name") or "").lower() == sci_name.lower():
            rec = (item.get("taxonInformation") or {}).get("recommendedSwedishName")
            if rec:
                return _clean(rec), "sweden_artdatabanken"
    return None, "sweden_no_match"


# ---------- GBIF ----------

GBIF_COL_DATASET = "7ddf754f-d193-4cc9-b351-99906754a03b"


def gbif(sci_name: str, target: str) -> tuple[str | None, str]:
    params = urllib.parse.urlencode({
        "datasetKey": GBIF_COL_DATASET,
        "nameType": "SCIENTIFIC",
        "q": sci_name,
    })
    try:
        data = _http_get_json(f"https://api.gbif.org/v1/species/search?{params}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "gbif_lookup_failed"
    target_iso3 = GBIF_INV.get(target.lower())
    for result in (data or {}).get("results") or []:
        if (result.get("canonicalName") or "").lower() != sci_name.lower():
            continue
        for vn in result.get("vernacularNames") or []:
            if not target_iso3:
                # Some GBIF entries use 2-letter codes directly; try that fallback.
                if (vn.get("language") or "").lower() == target.lower() and vn.get("vernacularName"):
                    return _clean(vn["vernacularName"]), "gbif"
                continue
            if (vn.get("language") or "").lower() == target_iso3 and vn.get("vernacularName"):
                return _clean(vn["vernacularName"]), "gbif"
    return None, "gbif_no_match"


# ---------- Wikispecies interwiki ----------

PAREN_RE = re.compile(r"\s*\([^)]*\)")


def wikispecies(sci_name: str, target: str) -> tuple[str | None, str]:
    page = sci_name.replace(" ", "_")
    try:
        data = _http_get_json(
            f"https://api.wikimedia.org/core/v1/wikispecies/page/{urllib.parse.quote(page)}/links/language"
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "wikispecies_lookup_failed"
    if not isinstance(data, list):
        return None, "wikispecies_unexpected_shape"
    for link in data:
        if (link.get("code") or "").lower() != target.lower():
            continue
        title = link.get("title") or ""
        cleaned = PAREN_RE.sub("", title).strip()
        if cleaned and cleaned != sci_name:
            return _clean(cleaned), "wikispecies"
    return None, "wikispecies_no_match"


# ---------- iNaturalist ----------

def inaturalist(sci_name: str, target: str) -> tuple[str | None, str]:
    params = urllib.parse.urlencode({
        "q": sci_name,
        "per_page": "1",
        "locale": target,
    })
    try:
        data = _http_get_json(f"https://api.inaturalist.org/v1/taxa/autocomplete?{params}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None, "inaturalist_lookup_failed"
    for r in (data or {}).get("results") or []:
        if (r.get("name") or "").lower() == sci_name.lower() and r.get("preferred_common_name"):
            return _clean(r["preferred_common_name"]), "inaturalist"
    return None, "inaturalist_no_match"


# ---------- Cascade ----------

def _accept(candidate: str | None, *, source_value: str | None, sci_name: str) -> bool:
    """Filter out clearly-bad candidates: empty, same as the source-lang string, or same as the scientific name."""
    if not candidate:
        return False
    c = candidate.strip().lower()
    if not c:
        return False
    if source_value and c == source_value.strip().lower():
        return False
    if c == sci_name.strip().lower():
        return False
    return True


def resolve(
    *,
    sci_name: str,
    sci_name_id: str | None,
    target: str,
    source_value: str | None = None,
    sleep_s: float = 0.0,
) -> tuple[str | None, list[str]]:
    """Return (vernacular_or_none, [trace of source notes]).

    Candidates that collide with the source-language string (e.g. data-quality
    issue where another language's name is mis-tagged as the target) are
    rejected and the cascade continues to the next source.
    """
    trace: list[str] = []

    def try_(v: str | None, note: str) -> str | None:
        if _accept(v, source_value=source_value, sci_name=sci_name):
            trace.append(note)
            return v
        trace.append(note + ("_collision" if v else ""))
        return None

    # 1. NBIC by sciNameId (preferred), or by name.
    if sci_name_id:
        v, note = nbic_by_sci_name_id(sci_name_id, target)
    else:
        v, note = nbic_by_sci_name(sci_name, target)
    accepted = try_(v, note)
    if accepted:
        return accepted, trace
    if sleep_s:
        time.sleep(sleep_s)

    # 2. Sweden Artdatabanken (sv only).
    if target.lower() == "sv":
        v, note = sweden_artdatabanken(sci_name)
        accepted = try_(v, note)
        if accepted:
            return accepted, trace
        if sleep_s:
            time.sleep(sleep_s)

    # 3. GBIF.
    v, note = gbif(sci_name, target)
    accepted = try_(v, note)
    if accepted:
        return accepted, trace
    if sleep_s:
        time.sleep(sleep_s)

    # 4. Wikispecies.
    v, note = wikispecies(sci_name, target)
    accepted = try_(v, note)
    if accepted:
        return accepted, trace
    if sleep_s:
        time.sleep(sleep_s)

    # 5. iNaturalist.
    v, note = inaturalist(sci_name, target)
    accepted = try_(v, note)
    if accepted:
        return accepted, trace

    return None, trace


# ---------- CLI ----------

def _load_cache(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_cache(path: Path | None, cache: dict[str, dict]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("strings", type=Path)
    p.add_argument("--target", required=True)
    p.add_argument("--out-resolved", type=Path, required=True)
    p.add_argument("--out-remainder", type=Path, required=True)
    p.add_argument("--cache", type=Path, default=Path("work/adapter_cache.json"))
    p.add_argument("--sleep", type=float, default=0.1,
                   help="Seconds to pause between API calls (politeness throttle).")
    p.add_argument("--only-kind", default="vernacular_name",
                   help="Only consider records of this kind (default: vernacular_name)")
    args = p.parse_args(argv)

    cache = _load_cache(args.cache)
    resolved: list[dict] = []
    remainder: list[dict] = []
    counts = {
        "resolved_from_cache": 0,
        "resolved_live": 0,
        "unresolved_from_cache": 0,
        "unresolved_live": 0,
        "skipped": 0,
    }
    source_counts: dict[str, int] = {}

    for line in args.strings.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        kind = rec.get("kind")
        ctx = rec.get("context") or {}
        sci_name = ctx.get("scientificName")
        ext_ref = ctx.get("externalReference") or {}
        sci_name_id = ext_ref.get("externalId") if (ext_ref.get("serviceId") or "").endswith("nbic_taxa") else None

        if kind != args.only_kind or not sci_name:
            remainder.append(rec)
            counts["skipped"] += 1
            continue

        cache_key = f"{sci_name}|{args.target}"
        was_cached = cache_key in cache
        if was_cached:
            entry = cache[cache_key]
            target_val = entry.get("target")
        else:
            target_val, trace = resolve(
                sci_name=sci_name,
                sci_name_id=sci_name_id,
                target=args.target,
                source_value=rec.get("source"),
                sleep_s=args.sleep,
            )
            entry = {"target": target_val, "trace": trace}
            cache[cache_key] = entry
            # Track which source produced the hit (last note in trace).
            if target_val and trace:
                source_counts[trace[-1]] = source_counts.get(trace[-1], 0) + 1

        if target_val:
            out_rec = {
                **rec,
                "target": target_val,
                "source_provenance": entry.get("trace", []),
            }
            resolved.append(out_rec)
            counts["resolved_from_cache" if was_cached else "resolved_live"] += 1
        else:
            remainder.append({**rec, "adapter_trace": entry.get("trace", [])})
            counts["unresolved_from_cache" if was_cached else "unresolved_live"] += 1

    _save_cache(args.cache, cache)

    args.out_resolved.parent.mkdir(parents=True, exist_ok=True)
    args.out_remainder.parent.mkdir(parents=True, exist_ok=True)
    args.out_resolved.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resolved) + ("\n" if resolved else ""),
        encoding="utf-8",
    )
    args.out_remainder.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in remainder) + ("\n" if remainder else ""),
        encoding="utf-8",
    )

    resolved_total = counts["resolved_from_cache"] + counts["resolved_live"]
    unresolved_total = counts["unresolved_from_cache"] + counts["unresolved_live"]
    print(
        f"Adapter [{args.only_kind} → {args.target}]: "
        f"{resolved_total} resolved "
        f"({counts['resolved_live']} live, {counts['resolved_from_cache']} cached), "
        f"{unresolved_total} unresolved "
        f"({counts['unresolved_live']} live, {counts['unresolved_from_cache']} cached), "
        f"{counts['skipped']} skipped (not target kind).",
        file=sys.stderr,
    )
    if source_counts:
        print("Source breakdown (live hits):", source_counts, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
