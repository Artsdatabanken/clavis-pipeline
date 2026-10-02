#!/usr/bin/env python3
"""Tell the orchestrator what to do next, with every path filled in.

Usage:
  plan.py --sources DIR --taxa species.csv --lang nb --taxon Rodentia [--model opus]

Looks at what exists under DIR/work and prints the next phase: the exact
commands to run, and for agent phases one brief per agent written to
DIR/work/briefs/<name>.md (invariant lines first, specifics last). Run it
again after each phase; it is idempotent and never writes outside work/briefs.

Phases, detected from files:
  0  no work/run-start.txt                  -> write it; prepare sources (pdftotext, names, sections, figures)
  0c sources prepared, no claims.jsonl      -> one harvester brief per source
  1  claims.jsonl, no key                   -> one digitizer brief per source
  2  key, no *.audited.json                 -> one auditor brief per key
  3  all audited, no merge/07-hierarchy.json -> merge commands (union, draft spec, reconcile, cleanup, hierarchy)
  3b hierarchy, no merge/determinable.json  -> usability brief
  4  determinable key, no leveranse/gates.md -> coarsen, finalize, metadata, vernacular, run_gates
  done
A source given as a Clavis JSON file goes through refine + audit instead of harvest + digitize.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
INVARIANT = """Pipeline repository: {repo}
Read {repo}/AGENTS.md first, then invoke the skill named below and follow it.
Never write outside your output folder and scratch directory. Never open another source or key.
"""


def slug(p: Path) -> str:
    """Short ascii folder name from a source file: the first word of the name
    ('Bjärvall & Ullström - 1997 - ...' -> 'bjarvall', 'Pattedyrkompendium 2019.pdf' -> 'pattedyrkompendium')."""
    import unicodedata
    s = unicodedata.normalize("NFKD", p.stem).encode("ascii", "ignore").decode()
    m = re.search(r"[A-Za-z]+", s)
    return (m.group(0).lower() if m else "source")[:24]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--taxa", type=Path, required=True)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--taxon", required=True)
    ap.add_argument("--model", default="opus")
    a = ap.parse_args()
    S = a.sources.resolve(); W = S / "work"; B = W / "briefs"; D = S / "leveranse"
    B.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(S.glob("*.pdf")) + sorted(S.glob("*.PDF"))
    keys_in = [p for p in sorted(S.glob("*.json")) if p.name not in ("pages.json",)]
    srcs = {slug(p): p for p in pdfs}
    inv = INVARIANT.format(repo=REPO)
    py = sys.executable
    H = REPO / "skills/harvest-claims/scripts"

    def brief(name: str, skill: str, agent: str, body: str) -> Path:
        p = B / f"{name}.md"
        p.write_text(inv + f"Skill: {skill}\nAgent role: {agent}\nModel: {a.model}\n\n" + body, encoding="utf-8")
        return p

    if not (W / "run-start.txt").exists():
        W.mkdir(exist_ok=True)
        (W / "run-start.txt").write_text(datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + "\n")
        print("Phase 0: prepare each source (run these, then plan.py again):")
        for s, p in srcs.items():
            w = W / s; w.mkdir(exist_ok=True)
            print(f'  pdftotext -layout "{p}" "{w}/full.txt"')
            print(f'  {py} {H}/taxon_names.py "{a.taxa}" --lang {a.lang} --out "{W}/names.json"')
            print(f'  {py} {H}/find_sections.py "{w}/full.txt" --taxa "{a.taxa}" --names "{W}/names.json" --out "{w}/"')
            print(f'  {py} {H}/find_figures.py "{p}" --pages <section from {w}/pages.json> --text "{w}/full.txt" --out "{w}/figures.json" --render "{w}/figures/"')
            print(f"  then read the first and last page of the section in {w}/section.txt and confirm or adjust (--pages-override).")
        for k in keys_in:
            print(f"  Clavis source {k.name}: refine-clavis-key then audit-clavis-key (structural phases), output under {W}/{slug(k)}/")
        return 0

    todo = []
    for s, p in srcs.items():
        w = W / s
        if not (w / "claims.jsonl").exists():
            if not (w / "pages.json").exists():
                print(f"{s}: not prepared yet (no pages.json); finish Phase 0 first"); return 1
            todo.append(brief(f"harvest-{s}", "harvest-claims", "clavis-harvester",
                              f"Source folder: {w}\nTaxon list: {a.taxa}\nLanguage: {a.lang}\nOutput: {w}/claims/<Taxon>.jsonl per taxon, then {w}/claims.jsonl\nScratch: {w}/scratch/harvest/\nFigures: {w}/figures.json (crops in {w}/figures/)\n"))
    if todo:
        print("Phase 0c: spawn one clavis-harvester per source with these briefs:"); [print(f"  {t}") for t in todo]; return 0

    for s, p in srcs.items():
        w = W / s
        if not list(w.glob(f"{s}.*.json")) or not (w / "provenance.jsonl").exists():
            todo.append(brief(f"digitize-{s}", "digitize-clavis-key", "clavis-digitizer",
                              f"Claims: {w}/claims.jsonl\nTaxon list: {a.taxa}\nLanguage: {a.lang}\nOutput key: {w}/{s}.{a.taxon.lower()}.json (plus provenance.jsonl, skipped.jsonl, design.json, decisions.md, coverage.md next to it)\nTitle: {a.taxon} ({p.stem})\nGeography: the source's own coverage\nLicence: https://creativecommons.org/licenses/by/4.0/\nScratch: {w}/scratch/digitize/\nStart with: {py} {REPO}/skills/digitize-clavis-key/scripts/draft_design.py {w}/claims.jsonl --taxa {a.taxa} --lang {a.lang} --out {w}/design.draft.json --review {w}/design.review.md\n"))
    if todo:
        print("Phase 1: spawn one clavis-digitizer per source with these briefs:"); [print(f"  {t}") for t in todo]; return 0

    for s, p in srcs.items():
        w = W / s
        keys = [k for k in w.glob(f"{s}.*.json") if ".audited" not in k.name and "design" not in k.name]
        if keys and not list(w.glob("*.audited.json")):
            todo.append(brief(f"audit-{s}", "audit-clavis-key", "clavis-auditor",
                              f"Key: {keys[0]}\nClaims: {w}/claims.jsonl\nProvenance: {w}/provenance.jsonl\nSkipped: {w}/skipped.jsonl\nDesign: {w}/design.json\nDecisions: {w}/decisions.md\nOutput: {w}/{keys[0].stem}.audited.json, provenance.audited.jsonl, skipped.audited.jsonl, audit-findings.md\nScratch: {w}/scratch/audit/\n"))
    if todo:
        print("Phase 2: spawn one clavis-auditor per key with these briefs:"); [print(f"  {t}") for t in todo]; return 0

    M = W / "merge"; M.mkdir(exist_ok=True)
    MS = REPO / "skills/merge-clavis-keys/scripts"
    audited = sorted(set(W.glob("*/*.audited.json")))
    if not (M / "07-hierarchy.json").exists():
        print("Phase 3: merge (run in order; decide spec.json by meaning where the todo file says):")
        print(f'  cp "{a.taxa}" "{M}/species.csv"')
        alias = f' --alias "{M}/alias.json"' if (M / "alias.json").exists() else ""
        print(f"  resolve every source name through the taxonomy adapter; synonyms with evidence go to {M}/alias.json, then:")
        print(f'  {py} {MS}/union_keys.py --csv "{M}/species.csv"{alias} --out "{M}/03-union.json" ' + " ".join(f'"{k}"' for k in audited))
        print(f'  {py} {MS}/concordance_candidates.py "{M}/03-union.json" --out "{M}/candidates.md"')
        print(f'  {py} {MS}/draft_spec.py "{M}/03-union.json" --out "{M}/spec.json" --todo "{M}/spec.todo.md" --lang {a.lang}')
        print(f"  edit {M}/spec.json per spec.todo.md and candidates.md (meaning, not wording), then:")
        print(f'  {py} {MS}/reconcile.py "{M}/03-union.json" "{M}/spec.json" "{M}/04-reconciled.json" --lang {a.lang}')
        print(f'  mark location characters in {M}/spec.json with "location": true, then:')
        print(f'  {py} {MS}/cleanup_location.py "{M}/04-reconciled.json" "{M}/05-cleaned.json" --spec "{M}/spec.json" --removed "{M}/05-removed.json"')
        print(f'  {py} {MS}/choose_hierarchy.py "{M}/species.csv"')
        print(f'  {py} {MS}/build_hierarchy.py "{M}/05-cleaned.json" "{M}/07-hierarchy.json" --root {a.taxon} --rank <rank> --cache "{M}/species.csv.taxonomy-cache.json"')
        return 0
    if not (M / "determinable.json").exists():
        t = brief("usability", "determinability-pass", "clavis-usability",
                  f"Key: {M}/07-hierarchy.json\nLanguage: {a.lang}\nOutput: {M}/determinable.json, {M}/neighbours.json, rename files in {M}/determinability/, removed entries in {M}/removed.determinability.json, determinability-report.md\nScratch: {M}/scratch/usability/\n")
        print(f"Phase 3b: spawn clavis-usability with brief {t}"); return 0
    if not (D / "gates.md").exists():
        D.mkdir(exist_ok=True)
        key = D / f"{a.taxon.lower()}.json"
        print("Phase 4: coarsen, finalize, metadata, vernacular, gates (loop until all required gates pass):")
        print(f'  {py} {MS}/coarsen.py "{M}/determinable.json" "{M}/08-coarsened.json" --neighbours "{M}/neighbours.json" --workdir "{M}/coarsen/" --log "{M}/coarsen-log.json"')
        print(f'  {py} {MS}/finalize.py "{M}/08-coarsened.json" "{M}/09-final.json" --removed "{M}/09-zero-power.json" --order "{M}/order.json"')
        print(f"  add metadata (title, geography, licence, lastModified) -> {key}; merge removed files into {M}/removed.json")
        print(f'  {py} {MS}/vernacular.py "{key}" --lang {a.lang}')
        renames = sorted(glob.glob(str(M / "determinability" / "*.json"))) + sorted(glob.glob(str(M / "coarsen" / "step-[0-9][0-9].json")))
        alias = f' --alias "{M}/alias.json"' if (M / "alias.json").exists() else ""
        print(f'  {py} {REPO}/skills/build-clavis-key/scripts/run_gates.py "{key}" --csv "{M}/species.csv" --sources "{W}" --out "{D}" --spec "{M}/spec.json"{alias} --removed "{M}/removed.json" ' + " ".join(f'--rename "{r}"' for r in renames) + ' --source-keys ' + " ".join(f'"{k}"' for k in audited) + f' --run-start "{W}/run-start.txt" --match {S.name}')
        return 0
    print("Done: leveranse/gates.md exists. Write the final report from it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
