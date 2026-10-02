#!/usr/bin/env python3
"""List the figures in a source so harvesters read figure crops instead of
whole pages.

Usage:
  find_figures.py BOOK.pdf --pages 52-118 --out work/<source>/figures.json [--text BOOK.full.txt] [--render work/<source>/figures/] [--dpi 150]

Backends, tried in this order, results merged per page:
  1. layout.json next to the text file, if tools/ocr_pdf.py --layout wrote one
     for a scanned book: Surya layout regions labelled Figure/Picture/Table,
     with bounding boxes. The best signal for scans.
  2. pdfimages -list (poppler): embedded images per page with their size.
     Born-digital PDFs list each illustration; a scanned book lists one
     page-sized image per page, which is ignored (covers > 80% of the page).
  3. The text layer: pages whose text is much shorter than their neighbours
     (a full-page plate). No caption words of any language; short lines ending
     in a number on such a page are attached as caption text.

Output: figures.json = [{"page": N, "bbox": [x0, y0, x1, y1] | null, "source": "layout|pdfimages|caption|sparse", "caption": "..."}]
With --render, each figure with a bbox is cropped to PNG (pdftoppm), and a
page without a bbox but with a caption or sparse text is rendered whole.
Harvesters get these PNGs; they open an untouched page only when its text is
unreadable.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# No caption words: a figure is found by Surya's layout (scans) or the PDF's
# embedded images (born-digital), and by pages whose text is much shorter than
# their neighbours. Caption text is attached when a short line ends in a number.
CAPTION = re.compile(r"^\s*\S{1,12}\.?\s*\d{1,3}\b.{0,80}$")


def parse_range(s: str) -> tuple[int, int]:
    a, b = s.split("-")
    return int(a), int(b)


def from_layout(layout_path: Path, lo: int, hi: int) -> list[dict]:
    out = []
    data = json.loads(layout_path.read_text(encoding="utf-8"))
    for page in data:
        n = page.get("page")
        if n is None or not (lo <= n <= hi):
            continue
        for r in page.get("regions", []):
            if r.get("label", "").lower() in ("figure", "picture", "image", "table", "plate"):
                out.append({"page": n, "bbox": r.get("bbox"), "source": "layout", "caption": r.get("caption", "")})
    return out


def from_pdfimages(pdf: Path, lo: int, hi: int) -> list[dict]:
    if not shutil.which("pdfimages"):
        return []
    r = subprocess.run(["pdfimages", "-list", "-f", str(lo), "-l", str(hi), str(pdf)], capture_output=True, text=True)
    out = []
    pagesize = {}
    if shutil.which("pdfinfo"):
        info = subprocess.run(["pdfinfo", "-f", str(lo), "-l", str(hi), str(pdf)], capture_output=True, text=True).stdout
        for m in re.finditer(r"Page\s+(\d+) size:\s+([\d.]+) x ([\d.]+)", info):
            pagesize[int(m.group(1))] = (float(m.group(2)), float(m.group(3)))
    for line in r.stdout.splitlines()[2:]:
        parts = line.split()
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        page, typ, w, h = int(parts[0]), parts[2], int(parts[3]), int(parts[4])
        if typ not in ("image", "stencil"):
            continue
        # a scan: one image covering the page; skip it (handled by layout/text)
        ps = pagesize.get(page)
        try:
            xppi, yppi = float(parts[12]), float(parts[13])
            wpt, hpt = w / xppi * 72, h / yppi * 72
        except (IndexError, ValueError, ZeroDivisionError):
            wpt = hpt = None
        if ps and wpt and hpt and wpt * hpt > 0.8 * ps[0] * ps[1]:
            continue
        if w * h < 40 * 40:
            continue  # ornaments, rules
        out.append({"page": page, "bbox": None, "source": "pdfimages", "caption": "", "px": [w, h]})
    return out


def is_scan(pdf: Path, lo: int) -> bool:
    """A scanned book lists one page-sized image per page. Sample two pages."""
    if not shutil.which("pdfimages"):
        return False
    r = subprocess.run(["pdfimages", "-list", "-f", str(lo), "-l", str(lo + 1), str(pdf)], capture_output=True, text=True, timeout=120)
    rows = [l.split() for l in r.stdout.splitlines()[2:] if l.strip() and l.split()[0].isdigit()]
    if not rows:
        return False
    per_page = {}
    for p in rows:
        per_page.setdefault(int(p[0]), []).append(int(p[3]) * int(p[4]))
    return all(len(v) == 1 and v[0] > 1_000_000 for v in per_page.values())


def from_text(text_path: Path, lo: int, hi: int) -> list[dict]:
    pages = text_path.read_text(encoding="utf-8", errors="replace").split("\f")
    out = []
    lengths = {i: len(p.strip()) for i, p in enumerate(pages, 1)}
    for i in range(lo, min(hi, len(pages)) + 1):
        p = pages[i - 1]
        caps = [l.strip() for l in p.splitlines() if CAPTION.match(l.strip())][:3]   # attached as text, never a signal by itself
        neigh = [lengths.get(j, 0) for j in (i - 2, i - 1, i + 1, i + 2) if j in lengths]
        if neigh and lengths[i] < 0.35 * (sum(neigh) / len(neigh)) and lengths[i] < 1500:
            out.append({"page": i, "bbox": None, "source": "sparse", "caption": "; ".join(caps)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", required=True, help="PDF page range a-b")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--text", type=Path, help="pdftotext output of the whole book (form-feed separated)")
    ap.add_argument("--layout", type=Path, help="layout.json from tools/ocr_pdf.py --layout")
    ap.add_argument("--render", type=Path, help="folder for PNG crops / page renders")
    ap.add_argument("--dpi", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=60, help="render at most this many whole pages (scans without layout)")
    a = ap.parse_args()
    lo, hi = parse_range(a.pages)

    figs: list[dict] = []
    if a.layout and a.layout.exists():
        figs += from_layout(a.layout, lo, hi)
    scan = is_scan(a.pdf, lo)
    if scan:
        print("scanned book: embedded-image listing skipped (one image per page); figures come from layout.json and the text heuristics")
    else:
        figs += from_pdfimages(a.pdf, lo, hi)
    if a.text and a.text.exists():
        figs += from_text(a.text, lo, hi)

    # merge: one entry per page per bbox; caption text attached to page entries
    by_page: dict[int, dict] = {}
    boxed = []
    for f in figs:
        if f.get("bbox"):
            boxed.append(f)
            continue
        e = by_page.setdefault(f["page"], {"page": f["page"], "bbox": None, "source": set(), "caption": ""})
        e["source"].add(f["source"])
        if f.get("caption") and not e["caption"]:
            e["caption"] = f["caption"]
    merged = boxed + [dict(e, source="+".join(sorted(e["source"]))) for e in sorted(by_page.values(), key=lambda e: e["page"])]
    merged.sort(key=lambda f: (f["page"], f["bbox"] or [0]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

    if a.render and shutil.which("pdftoppm"):
        a.render.mkdir(parents=True, exist_ok=True)
        done = set()
        for f in merged:
            n = f["page"]
            if f.get("bbox"):
                x0, y0, x1, y1 = f["bbox"]
                name = a.render / f"p-{n:03d}-{int(x0)}-{int(y0)}"
                subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", str(a.dpi), "-png", "-x", str(int(x0 * a.dpi / 72)), "-y", str(int(y0 * a.dpi / 72)),
                                "-W", str(int((x1 - x0) * a.dpi / 72)), "-H", str(int((y1 - y0) * a.dpi / 72)), "-singlefile", str(a.pdf), str(name)], capture_output=True)
                f["png"] = str(name) + ".png"
            elif n not in done and len(done) < a.max_pages:
                name = a.render / f"p-{n:03d}"
                subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", str(a.dpi), "-png", "-singlefile", str(a.pdf), str(name)], capture_output=True)
                f["png"] = str(name) + ".png"
                done.add(n)
        a.out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

    pages = sorted({f["page"] for f in merged})
    print(f"{len(merged)} figure entries on {len(pages)} of {hi - lo + 1} pages -> {a.out}")
    print("pages:", ", ".join(map(str, pages)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
