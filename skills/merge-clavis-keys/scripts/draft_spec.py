#!/usr/bin/env python3
"""Draft spec.json for reconcile.py from the union, so the merge agent fills
in blanks instead of writing the file.

Usage:
  draft_spec.py 03-union.json --out spec.draft.json --todo spec.todo.md [--glossary glossary.json] [--lang nb]

Grouping (conservative, by wording only; meaning is the agent's call):
  * source characters whose titles normalize to the same string, or map to the
    same glossary entry, form one canonical character
  * numerical source characters with the same normalized title and unit join it
  * every other source character becomes its own canonical character, listed
    in the todo file next to the candidates concordance_candidates.py found
Label maps:
  * a source label identical (normalized) to a canonical state label maps 1:1
  * numerical members get {}
  * every other label maps to null and is listed in the todo file; reconcile.py
    refuses a spec with nulls, so nothing slips through unmapped
Canonical state order: by frequency of use across sources.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harvest-claims" / "scripts"))
from claims_vs_key import unit_factor


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    return re.sub(r"[\s\-–—/,;:.()\[\]]+", " ", s).strip()


T = lambda o: next(iter((o.get("title") or {}).values()), "")
U = lambda c: " ".join(str(v) for v in c["unit"].values()) if isinstance(c.get("unit"), dict) else str(c.get("unit") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("union", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--todo", type=Path, required=True)
    ap.add_argument("--glossary", type=Path)
    ap.add_argument("--lang", default=None)
    a = ap.parse_args()
    d = json.loads(a.union.read_text(encoding="utf-8"))
    gl = {}
    if a.glossary:
        for k, vs in json.loads(a.glossary.read_text(encoding="utf-8")).items():
            for v in [k] + vs:
                gl[norm(v)] = k

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in d["characters"]:
        title, src = T(c).rsplit(" [", 1)
        src = src.rstrip("]")
        key = gl.get(norm(title), norm(title))
        if c.get("type") == "numerical":
            key = "NUM " + key          # one measurement per title; units are scaled below
        groups[key].append({"src": src, "title": title, "c": c})

    used_labels: dict[str, Counter] = defaultdict(Counter)
    for s in d["statements"]:
        if s["frequency"] > 0 and not isinstance(s["value"], list):
            used_labels[s["character"]][s["value"]] += 1
    label_of = {s["id"]: T(s) for c in d["characters"] for s in (c.get("states") or [])}

    spec, todo = {}, []
    for key, members in groups.items():
        canon = Counter(m["title"] for m in members).most_common(1)[0][0]
        types = Counter(m["c"].get("type", "exclusive") for m in members)
        typ = types.most_common(1)[0][0]
        entry = {"type": typ, "members": defaultdict(dict)}
        if typ == "numerical":
            entry["unit"] = Counter(U(m["c"]) for m in members).most_common(1)[0][0]
            for m in members:
                f = unit_factor(U(m["c"]), entry["unit"])
                key_title = m["title"]
                while key_title in entry["members"][m["src"]]:      # same title twice in one source: keep both
                    key_title += " (2)"
                entry["members"][m["src"]][key_title] = {} if f == 1.0 else {"scale": f}
                if f == 1.0 and U(m["c"]) != entry["unit"]:
                    todo.append(("unit", canon, m["src"], m["title"], f"unit {U(m['c'])!r} vs canonical {entry['unit']!r}: not convertible, decide"))
        else:
            freq = Counter()
            for m in members:
                for sid, n in used_labels[m["c"]["id"]].items():
                    freq[norm(label_of[sid])] += n
            canon_labels = {}
            for m in members:
                for s in m["c"].get("states") or []:
                    canon_labels.setdefault(norm(T(s)), T(s))
            states = [canon_labels[k] for k, _ in freq.most_common()] + sorted(v for k, v in canon_labels.items() if k not in freq)
            entry["states"] = states
            for m in members:
                mp = {}
                for s in m["c"].get("states") or []:
                    lab = T(s)
                    mp[lab] = [canon_labels[norm(lab)]] if norm(lab) in canon_labels else None
                    if mp[lab] is None:
                        todo.append(("label", canon, m["src"], m["title"], lab))
                entry["members"][m["src"]][m["title"]] = mp
        entry["members"] = dict(entry["members"])
        if len(members) == 1:
            todo.append(("lonely", canon, members[0]["src"], members[0]["title"], ""))
        spec[canon] = entry

    a.out.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    lonely = [t for t in todo if t[0] == "lonely"]
    labels = [t for t in todo if t[0] == "label"]
    units = [t for t in todo if t[0] == "unit"]
    L = [f"# Spec draft: what the agent must decide", "",
         f"{len(spec)} canonical characters from {len(d['characters'])} source characters; {len(lonely)} are still one source only; {len(labels)} labels unmapped (null in the draft; reconcile.py refuses nulls).", "",
         "## Characters from a single source", "",
         "Each is probably the same observable as a character from another source under a different wording. Check `candidates.md` (concordance_candidates.py) and merge by moving its member entry under the right canonical character, mapping its labels.", ""]
    L += [f"- {c} ({s}: {t})" for _, c, s, t, _ in lonely]
    L += ["", "## Labels to map", "", "Replace each null with a list of canonical labels (several when the source is vaguer than the canonical set), or [] when the label says nothing about this character.", ""]
    L += [f"- {c} / {s} / {t}: `{lab}` -> null" for _, c, s, t, lab in labels]
    if units:
        L += ["", "## Units that could not be converted", ""] + [f"- {c} / {s} / {t}: {why}" for _, c, s, t, why in units]
    a.todo.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(spec)} canonical characters -> {a.out}; {len(lonely)} single-source, {len(labels)} unmapped labels -> {a.todo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
