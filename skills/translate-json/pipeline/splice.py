"""Splice translated strings back into the original JSON document.

Reads the original JSON and a translations JSONL (records with `path` and
`target`), inserts the target-language string alongside the source string in
each language-keyed object, and updates the top-level `language` array.

Key order is preserved: the new target-language key is added directly after
the source-language key inside its containing object.

Usage:
    python -m pipeline.splice INPUT.json TRANSLATIONS.jsonl --target en --out OUTPUT.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

PATH_SEGMENT_RE = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def parse_path(path: str) -> list[str | int]:
    """Parse a path like 'characters[12].states[0].title.nb' into segments.

    The first segment may be a bare key (e.g. 'title' in 'title.nb'), so we
    prefix with '.' to normalize parsing.
    """
    if not path:
        return []
    norm = "." + path if not (path.startswith(".") or path.startswith("[")) else path
    out: list[str | int] = []
    for m in PATH_SEGMENT_RE.finditer(norm):
        key, idx = m.group(1), m.group(2)
        if key is not None:
            out.append(key)
        else:
            out.append(int(idx))
    return out


def _navigate(root: Any, segments: list[str | int]) -> Any:
    cur = root
    for seg in segments:
        cur = cur[seg]
    return cur


def _insert_after(d: dict, anchor_key: str, new_key: str, new_value: Any) -> None:
    """Insert (new_key, new_value) immediately after anchor_key, preserving order."""
    if new_key in d:
        d[new_key] = new_value
        return
    items = list(d.items())
    rebuilt: list[tuple[str, Any]] = []
    inserted = False
    for k, v in items:
        rebuilt.append((k, v))
        if k == anchor_key and not inserted:
            rebuilt.append((new_key, new_value))
            inserted = True
    if not inserted:
        # Anchor missing — append at end as fallback.
        rebuilt.append((new_key, new_value))
    d.clear()
    d.update(rebuilt)


def splice(
    data: Any,
    translations: list[dict],
    *,
    source_lang: str,
    target_lang: str,
) -> tuple[Any, list[dict]]:
    """Return (updated_data, problems). `translations` is a list of {path, target, ...}."""
    problems: list[dict] = []

    for tr in translations:
        path = tr.get("path")
        target = tr.get("target")
        if not path or target is None:
            problems.append({"path": path, "reason": "missing path or target"})
            continue

        segments = parse_path(path)
        if not segments or segments[-1] != source_lang:
            problems.append({"path": path, "reason": "path does not end with source lang"})
            continue

        try:
            parent = _navigate(data, segments[:-1])
        except (KeyError, IndexError, TypeError) as e:
            problems.append({"path": path, "reason": f"navigation failed: {e}"})
            continue

        if not isinstance(parent, dict):
            problems.append({"path": path, "reason": "parent is not an object"})
            continue

        _insert_after(parent, source_lang, target_lang, target)

    # Update the top-level "language" field.
    if isinstance(data, dict) and "language" in data:
        lang_field = data["language"]
        if isinstance(lang_field, str):
            if lang_field != target_lang:
                data["language"] = [lang_field, target_lang] if lang_field != target_lang else [lang_field]
        elif isinstance(lang_field, list):
            if target_lang not in lang_field:
                lang_field.append(target_lang)

    return data, problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Splice translations into a JSON doc.")
    p.add_argument("input", type=Path)
    p.add_argument("translations", type=Path, help="JSONL with {path, target, ...} per record")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)

    data = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    translations = [json.loads(line) for line in args.translations.read_text(encoding="utf-8").splitlines() if line.strip()]

    updated, problems = splice(data, translations, source_lang=args.source, target_lang=args.target)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Spliced {len(translations) - len(problems)} / {len(translations)} translations "
          f"into {args.out}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problems:", file=sys.stderr)
        for prob in problems[:10]:
            print(f"  {prob}", file=sys.stderr)
        if len(problems) > 10:
            print(f"  ... and {len(problems) - 10} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
