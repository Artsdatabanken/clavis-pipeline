#!/usr/bin/env python3
"""Phase 4 NARROW step: list characters whose state set looks like it
spans more than one observable axis. A multi-axis character has states
that aren't mutually exclusive observations on one trait — e.g. color
states sitting alongside pattern states, or proportion states sitting
alongside cross-profile states. A specimen in hand could legitimately
satisfy one state on each axis, so the user can't pick "the" state.

Heuristic flags (any one fires):
  1. **Modifier-prefix mix**: at least one state begins with a modifier
     word ("met", "with", "mit", "avec", "med", "uten", "zonder",
     "without", "naar", "voor"…) AND at least one sibling state is a
     bare term with no such prefix.
  2. **Compound vs simple mix**: ≥4 states, some with internal spaces
     (compound labels) and some without — indicates one set of states
     describes one axis as a single token while another set adds
     accessory info from a second axis.
  3. **Length spread**: shortest state label ≤5 chars AND longest ≥4×
     shortest — sibling states of dramatically different sentence-shape
     usually describe different axes.
  4. **Multi-clause prose**: ≥2 states each contain ≥2 semicolons or
     ≥3 commas in long labels (≥40 chars). Typical of dichotomous-key
     couplets transcoded verbatim: every state is a paragraph that
     bundles many axes (color; size; habitat; teeth count; …). The
     proper fix is to split one character per axis.

False-positive avoidance:
  - Quantitative characters (every state parses as a numeric range/value)
    are skipped.
  - "X-if-present-else-absent" patterns (one state == 'absent' /
    'afwezig' / 'ontbreekt' / 'no'-prefix etc., others all describe
    presence-of-feature) are flagged but Claude should classify them as
    Tier-3 acceptable single-axis at the judge step.

Output: per flagged character, list the state labels with context, so
Claude can decide whether to split and how. Decisions feed
`apply_character_split.py`.

Usage:
  ./venv/bin/python find_multi_axis_characters.py IN.json --out multi_axis.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

# Modifier-prefix words that often introduce a second axis.
MODIFIER_PREFIXES: dict[str, list[str]] = {
    "nl": ["met", "zonder", "naar", "voor", "achter", "in", "boven", "onder", "tussen"],
    "en": ["with", "without", "toward", "in front", "behind", "above", "below", "between"],
    "de": ["mit", "ohne", "nach", "vor", "hinter", "über", "unter", "zwischen"],
    "fr": ["avec", "sans", "vers", "devant", "derrière", "au-dessus", "en-dessous", "entre"],
    "nb": ["med", "uten", "mot", "foran", "bak", "over", "under", "mellom"],
    "nn": ["med", "utan", "mot", "framom", "bak", "over", "under", "mellom"],
    "es": ["con", "sin", "hacia", "delante", "detrás", "arriba", "abajo", "entre"],
    "sv": ["med", "utan", "mot", "framför", "bakom", "över", "under", "mellan"],
}

# Words that mark presence/absence (Tier-3 sentinel — script flags but Claude judges)
ABSENT_MARKERS: dict[str, list[str]] = {
    "nl": ["afwezig", "ontbreekt", "geen "],
    "en": ["absent", "missing", "no "],
    "de": ["fehlt", "abwesend", "kein "],
    "fr": ["absent", "manque", "sans "],
    "nb": ["fraværende", "mangler", "ingen "],
    "nn": ["fråverande", "manglar", "ingen "],
    "es": ["ausente", "falta", "sin "],
    "sv": ["saknas", "frånvarande", "ingen ", "inget "],
}

_QUANT_PATTERNS = [
    re.compile(r"^(-?\d+)\s*[–\-‒—]\s*(-?\d+)\s*(\S.*)?$"),
    re.compile(r"^<\s*(-?\d+)\s*(\S.*)?$"),
    re.compile(r"^>\s*(-?\d+)\s*(\S.*)?$"),
    re.compile(r"^(-?\d+)\s*(\S.*)?$"),
]


def parses_as_quant(label: str) -> bool:
    return any(p.match(label.strip()) for p in _QUANT_PATTERNS)


def primary_lang(clavis: dict) -> str:
    return (clavis.get("language") or ["en"])[0]


def loc(obj: dict | None, lang: str) -> str:
    if not obj:
        return ""
    return (obj.get(lang) or next(iter(obj.values()), "") or "").strip()


def has_modifier_prefix(label: str, prefixes: list[str]) -> bool:
    low = label.lower()
    return any(low.startswith(p + " ") for p in prefixes)


def has_absent_marker(label: str, markers: list[str]) -> bool:
    low = label.lower()
    return any(low == m.strip() or low.startswith(m) for m in markers)


def flag_character(c: dict, lang: str) -> tuple[bool, list[str]]:
    """Return (flagged, list of triggers)."""
    states = c.get("states") or []
    labels = [loc(s.get("title"), lang) for s in states]
    if len(labels) < 2:
        return False, []
    if all(parses_as_quant(l) for l in labels):
        return False, []  # all-numeric: not multi-axis

    triggers: list[str] = []
    prefixes = MODIFIER_PREFIXES.get(lang, [])
    markers = ABSENT_MARKERS.get(lang, [])

    n_modifier = sum(1 for l in labels if has_modifier_prefix(l, prefixes))
    n_simple = len(labels) - n_modifier - sum(1 for l in labels if has_absent_marker(l, markers))
    if 0 < n_modifier < len(labels) and n_simple >= 1:
        triggers.append(f"modifier-mix (n_modifier={n_modifier}, n_simple={n_simple})")

    n_compound = sum(1 for l in labels if " " in l)
    if len(labels) >= 4 and 0 < n_compound < len(labels):
        triggers.append(f"compound-mix (n_compound={n_compound}/{len(labels)})")

    lens = [len(l) for l in labels if l]
    if lens and min(lens) <= 5 and max(lens) >= 4 * min(lens):
        triggers.append(f"length-spread ({min(lens)}-{max(lens)})")

    n_multi_clause = sum(
        1 for l in labels
        if len(l) >= 40 and (l.count(";") >= 2 or l.count(",") >= 3)
    )
    if n_multi_clause >= 2:
        triggers.append(f"multi-clause-prose ({n_multi_clause}/{len(labels)})")

    # Couplets transcoded verbatim often separate axes with full sentences
    # ("Svans X. Öron Y. Kropp Z.") rather than commas/semicolons.
    n_multi_sentence = sum(
        1 for l in labels
        if len(l) >= 40 and len(re.findall(r"[.!?] +[A-ZÅÄÖÆØ(]", l)) >= 1
    )
    if n_multi_sentence >= 2:
        triggers.append(f"multi-sentence-prose ({n_multi_sentence}/{len(labels)})")

    return bool(triggers), triggers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, default=Path("multi_axis.md"))
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    lang = primary_lang(clavis)

    body: list[str] = []
    n_flagged = 0
    for c in clavis["characters"]:
        flagged, triggers = flag_character(c, lang)
        if not flagged:
            continue
        n_flagged += 1
        title = loc(c.get("title"), lang) or "(untitled)"
        labels = [loc(s.get("title"), lang) for s in (c.get("states") or [])]
        body.append(f"\n## {title}")
        body.append(f"Character ID: `{c['id']}`")
        body.append(f"Triggers: {', '.join(triggers)}\n")
        body.append("State labels (with state IDs):")
        for s in c.get("states") or []:
            body.append(f"  - {loc(s.get('title'), lang)!r}  (`{s['id']}`)")
        body.append("")

    header = [
        f"# Multi-axis character candidates: {args.infile.name}",
        "",
        f"Heuristic triggers: modifier-prefix mix, compound vs simple mix, "
        f"length spread ≥4× with shortest label ≤5 chars, or multi-clause prose "
        f"(≥2 states each ≥40 chars with ≥2 semicolons or ≥3 commas).",
        "",
        f"{n_flagged} flagged characters out of {len(clavis['characters'])}.",
        "",
        "For each, decide whether to split (and how) per Protocol 1 at the character level: "
        "states must partition observable values on **one** axis. If a specimen could "
        "legitimately satisfy one state on each of multiple axes (e.g. one color AND one pattern), "
        "the character is bundled and must split.",
        "",
        "**Tier-3 acceptable**: a character whose states are all observations on one axis "
        "*conditional on presence*, plus an 'absent' state (e.g. `afwezig` / `ontbreekt` "
        "alongside shape descriptors). Mark these as keep-as-is.",
    ]
    if n_flagged == 0:
        header.append("\n_No flagged characters — Phase 4 has nothing to do._\n")

    args.out.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  {n_flagged} flagged characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
