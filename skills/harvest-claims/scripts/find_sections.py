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
  <taxon>.txt     the pages where the taxon has a heading (plus the next page),
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
    ap.add_argument("--pdf", type=Path, help="the source PDF: per-taxon files are written in reading order (pdftotext without -layout), so two-column pages are not interleaved and quotes copied from them are verbatim in the book")
    ap.add_argument("--pages-override", type=Path,
                    help="JSON {taxon: [pdf pages or 'a-b' ranges]} set by the orchestrator after reading the "
                         "source; replaces the heuristic run for those taxa (books with an overview plate or "
                         "key ahead of the species accounts defeat 'first mention in section')")
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
    HEAD_MAX = 45          # a species heading is a short line (or a short column segment)
    COLGAP = re.compile(r"\s{3,}")   # two-column layouts: test each column segment as its own line
    SENTENCE = re.compile(r"[.,;:]\s*\S")   # sentence punctuation followed by text: body, not heading

    def heading_pages(t: str) -> list[int]:
        """Pages in the section with a heading-like line for the taxon: a short
        line, no sentence punctuation, with the Latin name (best) or a vernacular
        name at the start (inflected forms and all caps allowed). All
        such pages are returned: a book may treat a species in several places
        (overview, account, tracks, skull), and a species account may start on
        the overview's page."""
        g, *rest = t.split()
        latin = [re.compile(re.escape(t), re.I)]
        if rest:
            latin.append(re.compile(re.escape(g[0]) + r"\.\s*" + re.escape(" ".join(rest)), re.I))
        vern = [n for n in extra.get(t, []) if not re.match(r"^[A-Z]\.\s", n)]
        vern_rx = [re.compile(r"^" + re.escape(n) + r"[^\W\d_]{0,3}\b", re.I) for n in vern]   # inflected forms: up to three more letters, any language
        found = {}
        lo, hi = section
        for i in range(lo, hi + 1):
            strip_digits = lambda x: re.sub(r"\d+", "", x).strip()
            prev_lines = {strip_digits(l) for l in pages[i - 2].splitlines()} if i >= 2 else set()
            for line in pages[i - 1].splitlines():
                for s in COLGAP.split(line.strip()):
                    s = s.strip()
                    if not (2 < len(s) <= HEAD_MAX) or SENTENCE.search(s):
                        continue
                    if strip_digits(s) in prev_lines:
                        continue   # running header repeated from the previous page (page numbers ignored), not a heading
                    score = 3 if any(rx.match(s) for rx in latin) else 2 if any(rx.search(s) for rx in latin) else 1 if any(rx.match(s) for rx in vern_rx) else 0
                    if score:
                        found[i] = max(found.get(i, 0), score)
        return sorted(found)

    if section:
        for t, r in result.items():
            inside = [p for p in r["pages"] if section[0] <= p <= section[1]]
            if r["pages"] and not inside:
                back_matter.append(t)
            hp = heading_pages(t) if r["pages"] else []
            # pages where the taxon is mentioned three or more times are its account
            # even without a detectable heading (two-column plates, OCR noise)
            dense = [p for p in inside if sum(len(rx.findall(pages[p - 1])) for rx in patterns(t)) >= 3]
            if hp or dense:
                r["heading_pages"] = hp
                r["dense_pages"] = dense
                ps = set()
                for p in hp + dense:
                    ps.update((p, p + 1))        # the page and the one after it
                r["best"] = sorted(p for p in ps if section[0] <= p <= section[1])
            elif inside:
                # no heading found: the page with the most mentions inside the section
                dens = max(inside, key=lambda p: (sum(len(rx.findall(pages[p - 1])) for rx in patterns(t)), -p))
                r["best"] = [dens, dens + 1]

    # --pages-override: {"Taxon": [pdf pages]} replaces the detected pages
    override = json.loads(a.pages_override.read_text(encoding="utf-8")) if getattr(a, "pages_override", None) and a.pages_override.exists() else {}
    for t, ps in override.items():
        if t in result:
            pages_ = set()
            for p in ps:
                if isinstance(p, str) and "-" in p:
                    x, y = p.split("-"); pages_.update(range(int(x), int(y) + 1))
                else:
                    pages_.add(int(p))
            result[t]["best"] = sorted(pages_)
            result[t]["override"] = True

    a.out.mkdir(parents=True, exist_ok=True)
    meta = {"source_text": str(a.text), "pdf_pages": len(pages), "printed_page_offset": offset,
            "section_pdf_pages": section, "taxa": result,
            "taxa_whose_best_run_is_outside_the_section": back_matter,
            "not_found": [t for t, r in result.items() if not r["pages"]]}
    (a.out / "pages.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    def marker(i: int) -> str:
        printed = f" (printed page {i + offset})" if offset is not None else ""
        return f"\n===== PDF page {i}{printed} =====\n"

    import shutil, subprocess
    reading = {}

    def page_text(i: int) -> str:
        if a.pdf and shutil.which("pdftotext"):
            if i not in reading:
                r = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-enc", "UTF-8", str(a.pdf), "-"], capture_output=True, text=True)
                reading[i] = r.stdout if r.returncode == 0 and r.stdout.strip() else pages[i - 1]
            return reading[i]
        return pages[i - 1]

    def write_pages(path: Path, ps: list[int], head: str):
        body = [head]
        for i in ps:
            if 1 <= i <= len(pages):
                body.append(marker(i) + page_text(i))
        path.write_text("".join(body), encoding="utf-8")

    head = (f"# Source text: {a.text.name}. Page markers give the PDF page and, when known, the printed page; cite the printed page.\n"
            f"# Printed page = PDF page {offset:+d}.\n" if offset is not None else f"# Source text: {a.text.name}. Printed-page offset unknown; cite PDF pages.\n")
    if section:
        write_pages(a.out / "section.txt", list(range(section[0], section[1] + 1)), head)
    for t, r in result.items():
        if r["best"]:
            if r.get("override"):
                ps = r["best"]
            else:
                ps = r["best"]
            write_pages(a.out / (re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_") + ".txt"), ps,
                        head + (f"# Taxon: {t}. Pages chosen by the orchestrator: {ps}. All mentions on PDF pages: {r['pages']}\n" if r.get("override") else f"# Taxon: {t}. Pages with a heading for it (and the page after each). All mentions on PDF pages: {r['pages']}\n"))

    print(f"{len(pages)} PDF pages; printed-page offset {offset if offset is not None else 'unknown'}")
    print(f"proposed section: PDF pages {section}" if section else "no section found")
    for t, r in result.items():
        print(f"  {t:<36} best {r['best'][0] if r['best'] else '-':>4}-{r['best'][-1] if r['best'] else '-':<4} hits {r['hits']:>3}{'  (outside section)' if t in back_matter else ''}{'  NOT FOUND' if not r['pages'] else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
