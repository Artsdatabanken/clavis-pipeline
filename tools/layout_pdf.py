#!/usr/bin/env python3
"""Find figures, plates and tables on PDF pages with Surya's layout model and
write layout.json for harvest-claims/scripts/find_figures.py.

Usage: layout_pdf.py BOOK.pdf --pages 52-136 --out work/<source>/layout.json [--dpi 100] [--batch 8]

Each page is rendered with pdftoppm, Surya labels its regions, and the
regions labelled figure, picture, table or image are written with their
bounding box in PDF points (1/72 inch), the unit find_figures.py crops in:
  [{"page": 52, "regions": [{"label": "figure", "bbox": [x0, y0, x1, y1]}]}, ...]
Needs surya-ocr (and a GPU for reasonable speed); see guides/claude-code.md.
"""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path

WANTED = {"figure", "picture", "table", "image", "plate"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", required=True, help="PDF page range a-b")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=100)
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    if not shutil.which("pdftoppm"):
        sys.exit("pdftoppm (poppler) is needed to render pages")
    try:
        from PIL import Image
        from surya.layout import LayoutPredictor
    except ImportError as e:
        sys.exit(f"surya-ocr is not installed ({e}); see guides/claude-code.md")
    try:
        from surya.foundation import FoundationPredictor
        predictor = LayoutPredictor(FoundationPredictor())
    except (ImportError, TypeError):
        predictor = LayoutPredictor()
    lo, hi = map(int, a.pages.split("-"))
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-f", str(lo), "-l", str(hi), "-r", str(a.dpi), "-png", str(a.pdf), f"{tmp}/p"], check=True)
        files = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        scale = 72.0 / a.dpi
        for i in range(0, len(files), a.batch):
            chunk = files[i:i + a.batch]
            images = [Image.open(f).convert("RGB") for f in chunk]
            results = predictor(images)
            for f, res in zip(chunk, results):
                page = int(f.stem.split("-")[-1])
                regions = []
                for b in getattr(res, "bboxes", []):
                    label = str(getattr(b, "label", "")).lower()
                    if label in WANTED:
                        regions.append({"label": label, "bbox": [round(x * scale, 1) for x in b.bbox]})
                out.append({"page": page, "regions": regions})
            print(f"  pages {lo + i}..{lo + i + len(chunk) - 1}: {sum(len(p['regions']) for p in out)} regions so far", flush=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(len(p['regions']) for p in out)} figure/table regions on {len(out)} pages -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
