#!/usr/bin/env python3
"""Token and cost report for one pipeline run under Claude Code.

Claude Code writes one JSONL transcript per session and one per sub-agent
(~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl), each line
carrying the model and token usage of an assistant message. This script sums
them for a time window and prints a table per agent plus totals and a cost
estimate.

Usage:
  token_report.py --since "2026-10-01 21:38" --until "2026-10-01 23:15" --match Gnagere-run2 [--project DIR] [--out report.md]

--match is a regex tested against each transcript's first user message (the
agent's brief); use the sources folder name so other sessions running at the
same time are left out.

Times are local. --project defaults to every project folder under
~/.claude/projects. Prices are per million tokens and live in PRICES below;
update them when they change. Cache writes are billed at 1.25x input, cache
reads at the listed cache price.

Other harnesses: this reads Claude Code's transcript format only. Write the
equivalent for yours and report the same four numbers.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

# USD per million tokens: (input, output, cache_read). Cache write = input * 1.25.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-haiku-4-5": (1.0, 5.0, 0.10),
}


def parse_local(s: str) -> float:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").astimezone().timestamp()


def first_user_text(path: Path) -> str:
    for line in path.open(encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = d.get("message") or {}
        if d.get("type") == "user" and isinstance(m, dict):
            c = m.get("content")
            if isinstance(c, str):
                return c.strip()
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "text":
                        return b["text"].strip()
    return ""


def scan(path: Path, t0: float, t1: float):
    tot = collections.Counter()
    models = collections.Counter()
    first = last = None
    for line in path.open(encoding="utf-8"):
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = d.get("message") or {}
        u = m.get("usage") if isinstance(m, dict) else None
        if not u:
            continue
        ts = d.get("timestamp")
        t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else None
        if t is None or not (t0 <= t <= t1):
            continue
        first = first or t
        last = t
        models[m.get("model", "?")] += 1
        tot["input"] += u.get("input_tokens", 0) or 0
        tot["output"] += u.get("output_tokens", 0) or 0
        tot["cache_write"] += u.get("cache_creation_input_tokens", 0) or 0
        tot["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        tot["calls"] += 1
    return tot, models, first, last


def cost(tot, models) -> float | None:
    if not models:
        return None
    model = models.most_common(1)[0][0]
    # dated ids ("claude-haiku-4-5-20251001") are priced as their family id
    p = PRICES.get(model) or next((v for k, v in sorted(PRICES.items(), key=lambda kv: -len(kv[0])) if model.startswith(k)), None)
    if not p:
        return None
    i, o, cr = p
    return (tot["input"] * i + tot["cache_write"] * i * 1.25 + tot["cache_read"] * cr + tot["output"] * o) / 1e6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    ap.add_argument("--project", type=Path, help="a ~/.claude/projects/<dir>; default: all")
    ap.add_argument("--match", help="regex on the transcript's first user message, e.g. the sources folder name")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    t0, t1 = parse_local(a.since), parse_local(a.until)
    roots = [a.project] if a.project else [p for p in (Path.home() / ".claude/projects").iterdir() if p.is_dir()]
    rows = []
    for root in roots:
        for f in root.rglob("*.jsonl"):
            if "memory" in f.parts:
                continue
            if a.match and not re.search(a.match, first_user_text(f)):
                continue
            tot, models, first, last = scan(f, t0, t1)
            if tot["calls"]:
                rows.append((f, tot, models, first, last))
    rows.sort(key=lambda r: r[3])
    grand = collections.Counter()
    usd = 0.0
    priced = True
    lines = [f"# Token report {a.since} to {a.until}" + (f", agents matching /{a.match}/" if a.match else "") + "\n",
             "| agent | model | calls | input | cache write | cache read | output | USD |", "|---|---|---|---|---|---|---|---|"]
    for f, tot, models, first, last in rows:
        name = "sub-agent" if "subagents" in f.parts else "session"
        brief = first_user_text(f).splitlines()[0][:70] if first_user_text(f) else ""
        model = models.most_common(1)[0][0]
        c = cost(tot, models)
        if c is None:
            priced = False
        else:
            usd += c
        grand.update(tot)
        lines.append(f"| {name}: {brief} | {model} | {tot['calls']} | {tot['input']:,} | {tot['cache_write']:,} | {tot['cache_read']:,} | {tot['output']:,} | {c:.2f} |" if c is not None else
                     f"| {name}: {brief} | {model} | {tot['calls']} | {tot['input']:,} | {tot['cache_write']:,} | {tot['cache_read']:,} | {tot['output']:,} | ? |")
    lines.append(f"| **total** | | {grand['calls']} | {grand['input']:,} | {grand['cache_write']:,} | {grand['cache_read']:,} | {grand['output']:,} | {usd:.2f}{'' if priced else ' (+ unpriced)'} |")
    lines.append("")
    lines.append(f"{len(rows)} transcripts. Input that was served from cache costs a fraction of fresh input; 'cache read' is the bulk of a long run. Prices from PRICES in tools/token_report.py.")
    text = "\n".join(lines)
    print(text)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
