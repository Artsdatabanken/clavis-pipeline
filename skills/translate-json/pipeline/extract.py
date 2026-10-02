"""Extract translatable strings from a JSON document.

Detects language-keyed objects (BCP47 / ISO 639-1) anywhere in the document,
emits a JSONL stream of records describing each string to translate, and a
separate report of language-keyed objects whose values are non-string (e.g.
localized URL references) that need a different resolution path.

Usage:
    python -m pipeline.extract INPUT.json --source nb --out work/strings.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator

BCP47_KEY = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")

# Fields whose contents are scientific/Latin names — never translated.
NEVER_TRANSLATE_FIELDS = {"scientificName"}

# Pointer types that imply a value is a URL or reference object, not text.
NON_TEXT_VALUE_HINT_KEYS = {"serviceId", "externalId", "url", "href"}


@dataclass
class StringRecord:
    id: str            # stable id derived from path
    path: str          # JSON pointer to the language-keyed object's source value
    parent_path: str   # JSON pointer to the containing localized object
    field: str         # name of the field that owns the localized object (e.g. "title")
    kind: str          # heuristic: "scientific_name" | "vernacular_name" | "title" | "description" | "string"
    source: str        # the source-language string
    context: dict      # nearest contextual hints (parent character title, taxon, etc.)


@dataclass
class NonTextRecord:
    path: str
    field: str
    value: Any
    note: str


def _is_language_keyed_object(obj: Any) -> bool:
    """A dict whose keys all look like BCP47 codes and which is non-empty."""
    if not isinstance(obj, dict) or not obj:
        return False
    return all(isinstance(k, str) and BCP47_KEY.match(k) for k in obj.keys())


def _looks_like_url_ref(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(NON_TEXT_VALUE_HINT_KEYS & set(value.keys()))
    if isinstance(value, str):
        return value.startswith(("http://", "https://"))
    return False


def _classify_kind(field: str, source_value: str) -> str:
    if field == "vernacularName":
        return "vernacular_name"
    if field in {"title", "name", "label", "rank", "placeholderName", "audience", "unit"}:
        return "title"
    if field in {"description", "descriptionDetails", "source"}:
        return "description"
    return "string"


def _join_path(prefix: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{prefix}[{key}]"
    return f"{prefix}.{key}" if prefix else key


def _stable_id(path: str) -> str:
    # Path uniquely identifies position; convert to a compact id.
    return path.replace(".", "_").replace("[", "_").replace("]", "").replace("/", "_")


def _walk(
    node: Any,
    *,
    source_lang: str,
    path: str = "",
    field_name: str = "",
    ancestor_ctx: dict | None = None,
) -> Iterator[StringRecord | NonTextRecord]:
    ctx = dict(ancestor_ctx or {})

    if isinstance(node, dict):
        # Capture useful context as we descend.
        if isinstance(node.get("scientificName"), str):
            ctx["scientificName"] = node["scientificName"]
        if isinstance(node.get("id"), str):
            ctx["nearestId"] = node["id"]
        ext_ref = node.get("externalReference")
        if isinstance(ext_ref, dict) and ext_ref.get("serviceId") and ext_ref.get("externalId"):
            ctx["externalReference"] = {
                "serviceId": ext_ref["serviceId"],
                "externalId": ext_ref["externalId"],
            }

        if _is_language_keyed_object(node) and field_name not in NEVER_TRANSLATE_FIELDS:
            value = node.get(source_lang)
            if value is None:
                return
            if isinstance(value, str):
                source_value = value
                context: dict[str, Any] = {}
                if "scientificName" in ctx:
                    context["scientificName"] = ctx["scientificName"]
                if "externalReference" in ctx:
                    context["externalReference"] = ctx["externalReference"]
                # Keep nearestId only if it's the sole hint we have.
                if "nearestId" in ctx and not context:
                    context["nearestId"] = ctx["nearestId"]
                rec = StringRecord(
                    id=_stable_id(path + "." + source_lang),
                    path=_join_path(path, source_lang),
                    parent_path=path,
                    field=field_name,
                    kind=_classify_kind(field_name, source_value),
                    source=source_value,
                    context=context,
                )
                yield rec
            else:
                yield NonTextRecord(
                    path=_join_path(path, source_lang),
                    field=field_name,
                    value=value,
                    note="language-keyed non-string value (e.g. URL reference); needs domain adapter",
                )
            return  # do not descend into other language siblings

        for k, v in node.items():
            yield from _walk(
                v,
                source_lang=source_lang,
                path=_join_path(path, k),
                field_name=k,
                ancestor_ctx=ctx,
            )

    elif isinstance(node, list):
        # When walking a list, propagate the parent field name (e.g. "states", "children", "taxa")
        # but also extract richer context (parent title) from each item as we go.
        for i, item in enumerate(node):
            item_ctx = dict(ctx)
            # If the list belongs to a parent that had a localized title (e.g. character.states),
            # use the parent's source-language title as "parentTitle" for children.
            yield from _walk(
                item,
                source_lang=source_lang,
                path=_join_path(path, i),
                field_name=field_name,
                ancestor_ctx=item_ctx,
            )


def _enrich_sibling_context(records: list[StringRecord], data: Any, source_lang: str) -> None:
    """Attach a 'parentTitle' to records that sit inside a sibling list (e.g. states of a character).

    We do this in a second pass to avoid coupling _walk too tightly to the Clavis shape;
    any localized title found on a node that contains a list of children gets propagated
    down to the localized strings inside that list.
    """
    # Build a map: prefix path -> parent title (source-lang) of nearest enclosing node
    # with a "title.{source_lang}".
    # We index records by path and walk a parallel structure to find parent titles.
    titles_by_path: dict[str, str] = {}

    def collect_titles(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            t = node.get("title")
            if isinstance(t, dict) and isinstance(t.get(source_lang), str):
                titles_by_path[path] = t[source_lang]
            for k, v in node.items():
                collect_titles(v, _join_path(path, k))
        elif isinstance(node, list):
            for i, item in enumerate(node):
                collect_titles(item, _join_path(path, i))

    collect_titles(data)

    sorted_title_paths = sorted(titles_by_path.keys(), key=len, reverse=True)

    def _strip_last_segment(p: str) -> str:
        # Strip trailing ".key" or "[i]"
        cut_dot = p.rfind(".")
        cut_brk = p.rfind("[")
        cut = max(cut_dot, cut_brk)
        return p[:cut] if cut > 0 else ""

    for rec in records:
        # The node that owns rec's localized object: parent of rec.parent_path.
        owner_node_path = _strip_last_segment(rec.parent_path)
        # Find the longest title path that is a STRICT ancestor of owner_node_path.
        for tp in sorted_title_paths:
            if tp and owner_node_path.startswith(tp + ".") or (
                tp and owner_node_path.startswith(tp + "[")
            ):
                rec.context.setdefault("parentTitle", titles_by_path[tp])
                break


def extract(data: Any, source_lang: str) -> tuple[list[StringRecord], list[NonTextRecord]]:
    strings: list[StringRecord] = []
    non_text: list[NonTextRecord] = []
    for item in _walk(data, source_lang=source_lang):
        if isinstance(item, StringRecord):
            strings.append(item)
        else:
            non_text.append(item)
    _enrich_sibling_context(strings, data, source_lang)
    return strings, non_text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract translatable strings from a JSON doc.")
    p.add_argument("input", type=Path)
    p.add_argument("--source", required=True, help="Source language code (e.g. 'nb')")
    p.add_argument("--out", type=Path, required=True, help="Output JSONL path for strings")
    p.add_argument("--non-text-out", type=Path, default=None,
                   help="Optional output JSONL path for language-keyed non-string values")
    args = p.parse_args(argv)

    data = json.loads(args.input.read_text(encoding="utf-8"))
    strings, non_text = extract(data, args.source)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for rec in strings:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    if args.non_text_out is not None:
        args.non_text_out.parent.mkdir(parents=True, exist_ok=True)
        with args.non_text_out.open("w", encoding="utf-8") as f:
            for rec in non_text:
                f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    print(f"Extracted {len(strings)} translatable strings to {args.out}", file=sys.stderr)
    if non_text:
        print(f"Found {len(non_text)} language-keyed non-string values "
              f"(skipped; need domain adapter)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
