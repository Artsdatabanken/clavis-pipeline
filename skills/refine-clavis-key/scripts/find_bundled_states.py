#!/usr/bin/env python3
"""Phase 3 NARROW step: list states whose labels look like they bundle
distinguishable values (e.g. 'red, sometimes white', 'bruin/grijs').

A state is flagged if its label contains, in the file's primary language:
  - A slash character "/"
  - A word-level disjunction connector (Dutch *of*, English *or*,
    German *oder*, French *ou*, Norwegian *eller*, Spanish *o*).
  - A qualifier marker (Dutch *soms*/*zelden*/*vaak*; English *sometimes*/
    *rarely*/*often*/*usually*; etc.).

Quantitative characters (every state parses as a numeric range/value)
are skipped — Phase 1 already atomized those.

Output: a markdown report Claude reads to decide per-flagged-state
whether to split into atomic labels, with sibling-state context for
disambiguation. Decisions JSON format:
  {"splits": [{"state_id": "...", "atomic_labels": ["...", ...]}]}

Usage:
  ./venv/bin/python find_bundled_states.py IN.json --out bundles.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Language → list of word-level disjunction connectors.
DISJUNCTIONS: dict[str, list[str]] = {
    "nl": ["of"],
    "en": ["or"],
    "de": ["oder"],
    "fr": ["ou"],
    "nb": ["eller"],
    "nn": ["eller"],
    "no": ["eller"],
    "sv": ["eller"],
    "da": ["eller"],
    "es": ["o"],
}

# Language → list of qualifier/uncertainty markers.
QUALIFIERS: dict[str, list[str]] = {
    "nl": ["soms", "zelden", "vaak", "meestal", "doorgaans"],
    "en": ["sometimes", "rarely", "often", "usually", "occasionally", "mostly"],
    "de": ["manchmal", "selten", "oft", "meistens", "gewöhnlich"],
    "fr": ["parfois", "rarement", "souvent", "habituellement"],
    "nb": ["noen ganger", "sjelden", "ofte", "vanligvis"],
    "sv": ["ibland", "sällan", "ofta", "vanligtvis", "oftast"],
    "nn": ["av og til", "sjelden", "ofte", "vanlegvis"],
    "es": ["a veces", "raramente", "a menudo", "usualmente"],
}

_QUANT_PATTERNS: list[re.Pattern] = [
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


def is_quantitative_char(c: dict, lang: str) -> bool:
    states = c.get("states") or []
    if not states:
        return False
    return all(parses_as_quant(loc(s.get("title"), lang)) for s in states)


def flag_label(label: str, lang: str) -> list[str]:
    """Return list of triggers fired ('/', 'of', 'soms', 'comma+phrase', …)."""
    triggers: list[str] = []
    if "/" in label:
        triggers.append("slash")
    text_lower = label.lower()

    for word in DISJUNCTIONS.get(lang, []):
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            triggers.append(f"disjunction:{word}")
            break  # one match enough

    for word in QUALIFIERS.get(lang, []):
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            triggers.append(f"qualifier:{word}")
            break

    # Comma followed by lowercase letter (NL/EN/DE convention) often
    # indicates a continuation rather than a list, but commas in state
    # labels are unusual enough that we flag them. Skip for very short
    # labels (< 12 chars) where commas are usually formatting.
    if "," in label and len(label) >= 12:
        triggers.append("comma")

    return triggers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("infile", type=Path)
    ap.add_argument("--out", type=Path, default=Path("bundles.md"))
    args = ap.parse_args(argv)

    clavis = json.loads(args.infile.read_text(encoding="utf-8"))
    lang = primary_lang(clavis)

    body: list[str] = []
    n_flagged = 0
    n_chars = 0
    n_quant_skipped = 0

    for c in clavis["characters"]:
        title = loc(c.get("title"), lang) or "(untitled)"
        if is_quantitative_char(c, lang):
            n_quant_skipped += 1
            continue

        states = c.get("states") or []
        flagged: list[tuple[dict, str, list[str]]] = []
        for s in states:
            label = loc(s.get("title"), lang)
            triggers = flag_label(label, lang)
            if triggers:
                flagged.append((s, label, triggers))

        if not flagged:
            continue
        n_chars += 1
        n_flagged += len(flagged)
        sibling_labels = [loc(s.get("title"), lang) for s in states]
        body.append(f"\n## {title}")
        body.append(f"\nCharacter ID: `{c['id']}`")
        body.append(f"\nAll states (for context): {', '.join(repr(x) for x in sibling_labels)}\n")
        body.append("| Bundled state | State id | Triggers |")
        body.append("|---|---|---|")
        for s, label, triggers in flagged:
            body.append(f"| {label!r} | `{s['id']}` | {', '.join(triggers)} |")

    header = [
        f"# Bundled-state candidates: {args.infile.name}",
        "",
        f"Triggers (lang={lang}): slash, disjunction word ({DISJUNCTIONS.get(lang, [])}), "
        f"qualifier ({QUALIFIERS.get(lang, [])}), or comma in label ≥ 12 chars.",
        f"Skipped {n_quant_skipped} quantitative characters.",
        f"\n{n_flagged} flagged states across {n_chars} characters.",
    ]
    if n_flagged == 0:
        header.append("\n_No flagged states — Phase 3 has nothing to do._\n")

    args.out.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"  {n_flagged} states in {n_chars} characters (skipped {n_quant_skipped} quant chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
