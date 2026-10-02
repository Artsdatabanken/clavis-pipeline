"""Content-addressed translation cache.

Translations are keyed on a sha256 of (source, target_lang, glossary_version,
context_signature). A hit returns a previously-stored translation; a miss
adds the record to a "needs translation" set.

The cache is a single JSONL file (one record per line) for easy inspection and
diffing under version control.

Usage:
    python -m pipeline.cache filter STRINGS.jsonl --target en --cache CACHE.jsonl \
            --glossary-version GV --out-todo TODO.jsonl --out-resolved RESOLVED.jsonl

    python -m pipeline.cache store TRANSLATIONS.jsonl --target en --cache CACHE.jsonl \
            --glossary-version GV
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _context_signature(context: dict) -> str:
    # Stable signature for context; only keys that meaningfully affect translation.
    keep = {k: v for k, v in (context or {}).items() if k in {"parentTitle", "scientificName"}}
    return json.dumps(keep, sort_keys=True, ensure_ascii=False)


def cache_key(*, source: str, target_lang: str, glossary_version: str, context: dict) -> str:
    blob = json.dumps(
        {
            "source": source,
            "target_lang": target_lang,
            "glossary_version": glossary_version,
            "context": _context_signature(context),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out[rec["key"]] = rec
    return out


def append_cache(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_filter(args: argparse.Namespace) -> int:
    cache = load_cache(args.cache)
    todo: list[dict] = []
    resolved: list[dict] = []
    for line in args.strings.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        k = cache_key(
            source=rec["source"],
            target_lang=args.target,
            glossary_version=args.glossary_version,
            context=rec.get("context", {}),
        )
        rec["cache_key"] = k
        if k in cache:
            resolved.append({**rec, "target": cache[k]["target"]})
        else:
            todo.append(rec)
    args.out_todo.parent.mkdir(parents=True, exist_ok=True)
    args.out_resolved.parent.mkdir(parents=True, exist_ok=True)
    args.out_todo.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in todo) + ("\n" if todo else ""),
        encoding="utf-8",
    )
    args.out_resolved.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resolved) + ("\n" if resolved else ""),
        encoding="utf-8",
    )
    print(
        f"Cache: {len(resolved)} resolved from cache, {len(todo)} need translation",
        file=sys.stderr,
    )
    return 0


def cmd_store(args: argparse.Namespace) -> int:
    new_records: list[dict] = []
    for line in args.translations.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        k = rec.get("cache_key") or cache_key(
            source=rec["source"],
            target_lang=args.target,
            glossary_version=args.glossary_version,
            context=rec.get("context", {}),
        )
        new_records.append({
            "key": k,
            "source": rec["source"],
            "target": rec["target"],
            "target_lang": args.target,
            "glossary_version": args.glossary_version,
            "context": rec.get("context", {}),
        })
    # Deduplicate against existing cache.
    existing = load_cache(args.cache)
    to_append = [r for r in new_records if r["key"] not in existing]
    append_cache(args.cache, to_append)
    print(f"Cache: stored {len(to_append)} new entries (of {len(new_records)} submitted)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("filter", help="Split strings.jsonl into todo/resolved using the cache.")
    pf.add_argument("strings", type=Path)
    pf.add_argument("--target", required=True)
    pf.add_argument("--cache", type=Path, required=True)
    pf.add_argument("--glossary-version", default="")
    pf.add_argument("--out-todo", type=Path, required=True)
    pf.add_argument("--out-resolved", type=Path, required=True)
    pf.set_defaults(func=cmd_filter)

    ps = sub.add_parser("store", help="Store new translations into the cache.")
    ps.add_argument("translations", type=Path)
    ps.add_argument("--target", required=True)
    ps.add_argument("--cache", type=Path, required=True)
    ps.add_argument("--glossary-version", default="")
    ps.set_defaults(func=cmd_store)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
