"""Validate a JSON document against the schema referenced by its `$schema` key.

Caches fetched schemas under `work/schema_cache/` so repeated runs don't re-download.

Usage:
    python -m pipeline.validate FILE.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import jsonschema

CACHE_DIR = Path("work/schema_cache")


def _fetch_schema(url: str) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    cached = CACHE_DIR / f"{h}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    cached.write_text(body, encoding="utf-8")
    return json.loads(body)


def validate(file_path: Path) -> list[str]:
    """Return one human-readable line per error, including the failing message."""
    return [d["display"] for d in _validate_detailed(file_path)]


def _validate_detailed(file_path: Path) -> list[dict]:
    """Return rich error records: a stable `key` (for diffing) plus `display` text."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    schema_url = data.get("$schema")
    if not schema_url:
        return [{"key": "no-schema", "display": "document has no $schema field"}]
    schema = _fetch_schema(schema_url)
    validator = jsonschema.Draft202012Validator(schema)
    out: list[dict] = []
    for err in validator.iter_errors(data):
        abs_path = "/".join(str(p) for p in err.absolute_path)
        schema_path = "/".join(str(p) for p in err.absolute_schema_path)
        # Stable identity: where in the data, where in the schema, and which validator failed.
        key = f"{abs_path}|{schema_path}|{err.validator}"
        out.append({
            "key": key,
            "abs_path": abs_path,
            "validator": err.validator,
            "display": f"{abs_path} [{err.validator}]: {err.message[:200]}",
        })
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional baseline JSON. If provided, only report errors that did NOT exist in the baseline.",
    )
    args = p.parse_args(argv)
    detailed = _validate_detailed(args.input)
    keys = {d["key"] for d in detailed}
    if args.baseline:
        baseline_detailed = _validate_detailed(args.baseline)
        baseline_keys = {d["key"] for d in baseline_detailed}
        new_keys = keys - baseline_keys
        fixed_keys = baseline_keys - keys
        print(
            f"{args.input}: {len(detailed)} total error(s), "
            f"{len(new_keys)} new vs baseline, {len(fixed_keys)} fixed",
            file=sys.stderr,
        )
        if new_keys:
            print("NEW errors introduced (must investigate):", file=sys.stderr)
            for d in detailed:
                if d["key"] in new_keys:
                    print(f"  {d['display']}", file=sys.stderr)
            return 1
        print("OK: no new validation errors compared to baseline.", file=sys.stderr)
        return 0
    if not detailed:
        print(f"OK: {args.input} validates against its $schema", file=sys.stderr)
        return 0
    print(f"FAIL: {len(detailed)} validation error(s) in {args.input}", file=sys.stderr)
    for d in detailed[:50]:
        print(f"  {d['display']}", file=sys.stderr)
    if len(detailed) > 50:
        print(f"  ... and {len(detailed) - 50} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
