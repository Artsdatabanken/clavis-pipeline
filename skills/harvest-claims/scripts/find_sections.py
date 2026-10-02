#!/usr/bin/env python3
"""Find where each taxon is treated in a source's text layer, propose the
section range, compute the printed-page offset, and write one small text file
per taxon for the harvesters.

Usage:
  find_sections.py BOOK.full.txt --taxa species.csv --out work/<source>/ [--names names.json] [--min-hits 2]

Inputs
  BOOK.full.txt   pdftotext -layout output of the whole book, pages separated
                  by form feeds (\\f). PDF page i is text chunk i (1-based).
  species.csv     the species list (column scientificName); genus names and
                  any synonyms/vernaculars in names.json ({"Sorex minutus":
                  ["dvergspissmus", "S. minutus"]}) are searched too.

Outputs, in --out
  pages.json      per taxon: PDF pages with hits, the best run of pages, hit
                  counts; plus the proposed section range and the printed-page
                  offset (mode of printed_number - pdf_page over pages whose
                  header or footer carries a bare page number)
  <taxon>.txt     the taxon's pages (best run, padded by one page each side)
                  with "===== PDF page N (printed page M) =====" markers
  section.txt     the whole proposed section, same markers

Everything here is a hint for the orchestrator: it confirms the two edge
pages of the section by reading them, nothing else. Back matter (index,
glossary, literature) produces dense name hits; runs there are flagged when
they lie after the last run that also contains description-like text.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def pages_of(text: str) -> list[str]:
    return text.split("\f")


def page_number_offset(pages: list[str]) -> int | None:
    """Mode of printed - pdf over pages with a bare number in first/last lines."""
    diffs = Counter()
    for i, p in enumerate(pages, 1):
        lines = [l.strip() for l in p.splitlines() if l.strip()]
        cand = lines[:2] + lines[-2:]
        for l in cand:
            m = re.fullmatch(r"(\d{1,4})", l) or re.match(r"^(\d{1,4})\s{2,}\S", l) or re.search(r"\S\s{2,}(\d{1,4})$", l)
            if m:
                n = int(m.group(1))
                if 0 < n < 2000:
                    diffs[n - i] += 1
    if not diffs:
        return None
    off, n = diffs.most_common(1)[0]
    return off if n >= 3 else None


def runs(sorted_pages: list[int], gap: int = 2) -> list[list[int]]:
    out: list[list[int]] = []
    for p in sorted_pages:
        if out and p - out[-1][-1] <= gap:
            out[-1].append(p)
        else:
            out.append([p])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", type=Path)
    ap.add_argument("--taxa", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--names", type=Path, help="extra names per taxon, JSON {taxon: [names]}")
    ap.add_argument("--min-hits", type=int, default=2)
    a = ap.parse_args()

    pages = pages_of(a.text.read_text(encoding="utf-8", errors="replace"))
    offset = page_number_offset(pages)
    taxa = [r["scientificName"].strip() for r in csv.DictReader(a.taxa.open(encoding="utf-8-sig")) if r.get("scientificName", "").strip()]
    extra = json.loads(a.names.read_text(encoding="utf-8")) if a.names else {}

    def patterns(t: str) -> list[re.Pattern]:
        g, *rest = t.split()
        pats = [re.escape(t)]
        if rest:
            pats.append(re.escape(g[0]) + r"\.\s*" + re.escape(" ".join(rest)))  # S. minutus
        for n in extra.get(t, []):
            pats.append(re.escape(n))
        return [re.compile(p, re.I) for p in pats]

    low = [p.lower() for p in pages]
    result = {}
    all_hit_pages: Counter = Counter()
    for t in taxa:
        pats = patterns(t)
        hits = {}
        for i, p in enumerate(pages, 1):
            n = sum(len(rx.findall(p)) for rx in pats)
            if n:
                hits[i] = n
        if not hits:
            result[t] = {"pages": [], "best": [], "hits": 0}
            continue
        rs = runs(sorted(hits))
        # best run: most hits, ties broken by length
        best = max(rs, key=lambda r: (sum(hits[p] for p in r), len(r)))
        result[t] = {"pages": sorted(hits), "best": best, "hits": sum(hits.values()),
                     "hits_in_best": sum(hits[p] for p in best)}
        for p in best:
            all_hit_pages[p] += hits[p]

    # proposed section: the densest cluster of pages where listed taxa are
    # mentioned (any mention, not only best runs), gaps up to 10 pages; it
    # must contain at least half of the taxa that were found at all.
    page_taxa: dict[int, set] = defaultdict(set)
    for t, r in result.items():
        for p in r["pages"]:
            page_taxa[p].add(t)
    section = None
    found = [t for t, r in result.items() if r["pages"]]
    if page_taxa:
        clusters = runs(sorted(page_taxa), gap=10)
        clusters.sort(key=lambda c: (len({t for p in c for t in page_taxa[p]}), len(c)), reverse=True)
        for c in clusters:
            if len({t for p in c for t in page_taxa[p]}) >= max(1, len(found) // 2):
                section = [c[0], c[-1]]
                break
    back_matter = []
    if section:
        for t, r in result.items():
            inside = [p for p in r["pages"] if section[0] <= p <= section[1]]
            if r["pages"] and not inside:
                back_matter.append(t)
            # a taxon's own pages: from its first mention inside the section up to
            # the next taxon's first mention (species are treated one after another),
            # at most 6 pages; this replaces the hit-run when the name appears once
            if inside:
                r["best"] = [inside[0]]
        starts = sorted((r["best"][0], t) for t, r in result.items() if r["best"] and section[0] <= r["best"][0] <= section[1])
        for k, (p0, t) in enumerate(starts):
            p1 = starts[k + 1][0] - 1 if k + 1 < len(starts) else min(section[1], p0 + 5)
            p1 = max(p0, min(p1, p0 + 5))
            result[t]["best"] = list(range(p0, p1 + 1))

    a.out.mkdir(parents=True, exist_ok=True)
    meta = {"source_text": str(a.text), "pdf_pages": len(pages), "printed_page_offset": offset,
            "section_pdf_pages": section, "taxa": result,
            "taxa_whose_best_run_is_outside_the_section": back_matter,
            "not_found": [t for t, r in result.items() if not r["pages"]]}
    (a.out / "pages.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def marker(i: int) -> str:
        printed = f" (printed page {i + offset})" if offset is not None else ""
        return f"\n===== PDF page {i}{printed} =====\n"

    def write_pages(path: Path, ps: list[int], head: str):
        body = [head]
        for i in ps:
            if 1 <= i <= len(pages):
                body.append(marker(i) + pages[i - 1])
        path.write_text("".join(body), encoding="utf-8")

    head = (f"# Source text: {a.text.name}. Page markers give the PDF page and, when known, the printed page; cite the printed page.\n"
            f"# Printed page = PDF page {offset:+d}.\n" if offset is not None else f"# Source text: {a.text.name}. Printed-page offset unknown; cite PDF pages.\n")
    if section:
        write_pages(a.out / "section.txt", list(range(section[0], section[1] + 1)), head)
    for t, r in result.items():
        if r["best"]:
            ps = list(range(max(1, r["best"][0]), min(len(pages), r["best"][-1] + 1) + 1))
            write_pages(a.out / (re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_") + ".txt"), ps,
                        head + f"# Taxon: {t}. From its first mention in the section to the next taxon's, padded one page. All mentions on PDF pages: {r['pages']}\n")

    print(f"{len(pages)} PDF pages; printed-page offset {offset if offset is not None else 'unknown'}")
    print(f"proposed section: PDF pages {section}" if section else "no section found")
    for t, r in result.items():
        print(f"  {t:<36} best {r['best'][0] if r['best'] else '-':>4}-{r['best'][-1] if r['best'] else '-':<4} hits {r['hits']:>3}{'  (outside section)' if t in back_matter else ''}{'  NOT FOUND' if not r['pages'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
