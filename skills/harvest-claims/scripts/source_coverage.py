#!/usr/bin/env python3
"""Check the claims against the source text itself, in both directions.

Usage:
  source_coverage.py work/<source>/claims.jsonl work/<source>/full.txt --pages work/<source>/pages.json --pdf BOOK.pdf
                     [--decisions work/<source>/source-coverage.decisions.jsonl] --out work/<source>/source-coverage.md

1. Every claim's quote must occur in the source text (after normalizing case,
   punctuation, line breaks and hyphenation). A quote that is not there was
   invented, paraphrased or "corrected"; quotes are verbatim. Figure claims
   (kind "figure") are listed separately: their quote is a label in an image.
2. On the pages the harvester was given (the union of the taxa's pages in
   pages.json, re-extracted in reading order when --pdf is given), every
   stretch of GAP or more words in a row that no claim quotes is listed.
   Each must get a decision in the decisions file, one per gap or one per page:
     {"gap": "<id>", "decision": ..., "note": "..."}
     {"page": <pdf page>, "decision": ..., "note": "..."}
   decision: "no-observable-claim" | "not-a-listed-taxon" | "claim-added" |
   "unreadable". "claim-added" means the claim is now in claims.jsonl; the next
   run shows the stretch as quoted.
Language-neutral: tokens are runs of letters or digits in any script; sentence
ends are . ! ? ; two-column layouts from pdftotext -layout are split into
columns before sentences are cut.
Exit 1 when a quote is not found or a sentence is neither quoted nor decided.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import json
import re
import statistics
import sys
import unicodedata
from pathlib import Path

TOKEN = re.compile(r"\w+|[.!?;]", re.UNICODE)
GAP = 8   # eight unquoted words in a row is more than a heading or a page number, less than a fact-bearing clause


def columns(page: str) -> str:
    """pdftotext -layout puts two columns side by side; read the left column, then the right."""
    rows = []
    for line in page.splitlines():
        segs = [(m.start(), m.group()) for m in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|\s*$)", line)]
        rows.append(segs)
    seconds = [segs[1][0] for segs in rows if len(segs) >= 2]
    if len(seconds) < 5:
        return page
    split = statistics.median(seconds) - 2
    left = [" ".join(t for p, t in segs if p < split) for segs in rows]
    right = [" ".join(t for p, t in segs if p >= split) for segs in rows]
    return "\n".join(left) + "\n" + "\n".join(right)


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).replace("­", "")
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)          # hyphenation across a line break
    return s.lower()


def tokens(s: str) -> list[str]:
    return TOKEN.findall(norm_text(s))


def find(seq: list[str], sub: list[str]) -> int:
    """Exact token match; the first and last quote tokens may be the end and the
    start of a source word (a quote cut at a line-break hyphen)."""
    n = len(sub)
    if not n:
        return -1
    for i in range(len(seq) - n + 1):
        if n == 1:
            if seq[i] == sub[0]:
                return i
            continue
        if seq[i].endswith(sub[0]) and seq[i + n - 1].startswith(sub[-1]) and seq[i + 1:i + n - 1] == sub[1:-1]:
            return i
    return -1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("claims", type=Path)
    ap.add_argument("text", type=Path)
    ap.add_argument("--pages", type=Path, required=True)
    ap.add_argument("--decisions", type=Path)
    ap.add_argument("--pdf", type=Path, help="the source PDF: the given pages are re-extracted in reading order (pdftotext without -layout), which keeps multi-column text apart")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    pages = a.text.read_text(encoding="utf-8", errors="replace").split("\f")
    reading_order = {}
    meta = json.loads(a.pages.read_text(encoding="utf-8"))
    offset = meta.get("printed_page_offset") or 0
    given = sorted({p for t in meta["taxa"].values() for p in t.get("best", []) if 1 <= p <= len(pages)})
    if not given and meta.get("section_pdf_pages"):
        lo, hi = meta["section_pdf_pages"]; given = list(range(lo, hi + 1))
    claims = [json.loads(l) for l in a.claims.read_text(encoding="utf-8").splitlines() if l.strip()]
    decided = {}
    if a.decisions and a.decisions.exists():
        for l in a.decisions.read_text(encoding="utf-8").splitlines():
            if l.strip():
                d = json.loads(l); decided[d.get("gap") or d.get("sentence") or "page:%s" % d.get("page")] = d
    if a.pdf:
        for p in given:  # reading order per page, so quotes crossing columns or line breaks are found
            r = subprocess.run(["pdftotext", "-f", str(p), "-l", str(p), str(a.pdf), "-"], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                reading_order[p] = r.stdout

    # token stream per given page
    page_toks = {}
    for p in given:
        page_toks[p] = tokens(reading_order.get(p) or columns(pages[p - 1]))
    covered = {p: [False] * len(t) for p, t in page_toks.items()}

    not_found, figures, found = [], [], 0
    for c in claims:
        q = [x for x in tokens(c.get("quote", "")) if x not in ".!?;"]
        if not q:
            continue
        try:
            pdf = int(str(c["page"]).strip()) - offset
        except ValueError:
            pdf = None
        order = ([pdf, pdf - 1, pdf + 1] if pdf else []) + given
        hit = False
        for p in dict.fromkeys(x for x in order if x in page_toks):
            words = [x for x in page_toks[p] if True]
            # search on the page's word tokens with punctuation removed, then map back
            idx = [i for i, x in enumerate(words) if x not in ".!?;"]
            plain = [words[i] for i in idx]
            j = find(plain, q)
            if j >= 0:
                for k in range(j, j + len(q)):
                    covered[p][idx[k]] = True
                hit = True
                break
        if hit:
            found += 1
        elif c.get("kind") == "figure":
            figures.append(c)
        else:
            not_found.append(c)

    gaps = []
    for p, toks in page_toks.items():
        run = []
        for i, t in enumerate(toks + ["."]):
            if i < len(toks) and t not in ".!?;" and not covered[p][i]:
                run.append(i)
                continue
            if i < len(toks) and t not in ".!?;":
                pass
            if len(run) >= GAP:
                text = " ".join(toks[k] for k in run)
                gid = "g:" + hashlib.sha1(f"{p}|{text}".encode()).hexdigest()[:12]
                gaps.append({"id": gid, "page": p, "text": text})
            if i == len(toks) or t in ".!?;" or covered[p][i]:
                run = []
    page_decided = {d["page"] for d in decided.values() if "page" in d}
    gap_decided = {d["gap"] for d in decided.values() if "gap" in d}
    open_s = [g for g in gaps if g["id"] not in gap_decided and g["page"] not in page_decided]
    total_words = sum(1 for t in page_toks.values() for x in t if x not in ".!?;")
    quoted_words = sum(1 for p, t in page_toks.items() for i, x in enumerate(t) if x not in ".!?;" and covered[p][i])
    L = [f"# Source coverage: {a.claims.parent.name}", "",
         f"{len(claims)} claims; {found} quotes found in the text, {len(not_found)} not found, {len(figures)} figure labels (not in the text layer).",
         f"{len(given)} pages given to the harvester, {total_words} words, {quoted_words} inside quotes. {len(gaps)} stretches of {GAP}+ unquoted words: {len(gaps) - len(open_s)} decided, **{len(open_s)} open**.", ""]
    if not_found:
        L += ["## Quotes not found in the source (fix the quote to the verbatim text, or remove the claim)", ""]
        L += [f"- `{c.get('id', '?')}` {c['taxon']} p.{c['page']}: «{c['quote'][:140]}»" for c in not_found]
        L.append("")
    if open_s:
        L += [f"## Stretches of {GAP}+ words no claim quotes (add the missing claims, or decide each, or decide a whole page)", "",
              "Decisions go to source-coverage.decisions.jsonl: {\"gap\": id, \"decision\": ..., \"note\": ...} or {\"page\": n, \"decision\": ..., \"note\": ...}; decision is no-observable-claim | not-a-listed-taxon | claim-added | unreadable.", ""]
        cur = None
        for g in open_s:
            if g["page"] != cur:
                cur = g["page"]; L.append(f"### PDF page {cur} (printed {cur + offset})")
            L.append(f"- `{g['id']}` {g['text'][:240]}")
    a.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{found}/{len(claims)} quotes found, {len(not_found)} not found; {quoted_words}/{total_words} words quoted; {len(gaps)} gaps of {GAP}+ words, {len(open_s)} open -> {a.out}")
    return 1 if (not_found or open_s) else 0


if __name__ == "__main__":
    sys.exit(main())
