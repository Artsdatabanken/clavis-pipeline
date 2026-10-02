#!/usr/bin/env python3
"""OCR stitched JPGs and build a searchable PDF with Surya.

Pipeline:
1. Load page order from urls.txt (with [N...M] expansion, same as download).
2. For each page that doesn't yet have a per-page searchable PDF on disk:
   - Run Surya on the JPG to get text-line bboxes + text.
   - Build a one-page PDF: original JPG drawn full-bleed + invisible text
     layer positioned at each line's bbox (so copy/search work).
3. Merge per-page PDFs into the final book.pdf in urls.txt order.

Per-page PDFs live in nb_output/_searchable/<id>.pdf so the run is resumable.

Usage:
    python ocr_pdf.py               # uses urls.txt, writes book.pdf
    python ocr_pdf.py --no-merge    # only OCRs, skips final merge
    python ocr_pdf.py --lang no     # language hint (Surya autodetects otherwise)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Reduce CUDA fragmentation; must be set before torch is imported.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import pikepdf
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "sources" / "nb.no"))
from download_iiif import expand_range, safe_id  # noqa: E402


def init_surya():
    """Load Surya predictors. Imported lazily so --help is fast."""
    from surya.detection import DetectionPredictor
    from surya.foundation import FoundationPredictor
    from surya.recognition import RecognitionPredictor

    foundation = FoundationPredictor()
    return RecognitionPredictor(foundation), DetectionPredictor()


def ocr_batch(rec, det, image_paths, recognition_batch_size, detection_batch_size):
    imgs = [Image.open(p).convert("RGB") for p in image_paths]
    return rec(
        imgs,
        det_predictor=det,
        return_words=True,
        sort_lines=True,
        recognition_batch_size=recognition_batch_size,
        detection_batch_size=detection_batch_size,
    )


def gutter(band, W):
    """x of a clean vertical whitespace gap in the middle of a band, else None."""
    spans = sorted((e[1][0], e[1][2]) for e in band)
    gaps, end = [], spans[0][1]
    for x0, x1 in spans[1:]:
        if x0 - end > 0.015 * W and 0.3 * W < (end + x0) / 2 < 0.7 * W:
            gaps.append((x0 - end, (end + x0) / 2))
        end = max(end, x1)
    return max(gaps)[1] if gaps else None


def reading_order(entries, W):
    """Sort (text, bbox) entries into human reading order.

    Full-width lines (headings, wide captions) close a band; inside a band a
    clean vertical whitespace gap means two columns, read left then right.
    ponytail: covers 1-2 columns, which is what books use; 3+ columns fall
    back to row-major.
    """
    entries.sort(key=lambda e: (e[1][1], e[1][0]))
    out, band = [], []

    def flush():
        g = gutter(band, W) if len(band) > 1 else None
        if g:
            out.extend([e for e in band if e[1][2] <= g]
                       + [e for e in band if e[1][2] > g])
        else:
            out.extend(band)
        band.clear()

    for e in entries:
        x0, _, x1, _ = e[1]
        if x1 - x0 > 0.6 * W:
            flush()
            out.append(e)
        else:
            band.append(e)
    flush()
    return out


def make_page_pdf(jpg_path: Path, lines, out_path: Path):
    img = Image.open(jpg_path)
    W, H = img.size

    c = canvas.Canvas(str(out_path), pagesize=(W, H))
    c.drawImage(ImageReader(str(jpg_path)), 0, 0, width=W, height=H,
                preserveAspectRatio=False)

    # Build one text entry per detected line. Reconstruct line text from words
    # ordered left-to-right when available — Surya's word list isn't always
    # spatially ordered, and out-of-order words break copy-paste.
    entries = []
    for line in lines:
        words = getattr(line, "words", None) or []
        if words:
            ws = sorted(words, key=lambda w: w.bbox[0])
            s = " ".join((w.text or "").strip() for w in ws if (w.text or "").strip())
        else:
            s = (line.text or "").strip()
        if not s:
            continue
        entries.append((s, line.bbox))

    entries = reading_order(entries, W)

    text = c.beginText()
    text.setTextRenderMode(3)  # invisible: rendered to PDF text stream only
    for s, (x0, y0, x1, y1) in entries:
        line_h = max(y1 - y0, 1)
        line_w = max(x1 - x0, 1)
        font_size = line_h * 0.85
        tw = pdfmetrics.stringWidth(s, "Helvetica", font_size)
        text.setFont("Helvetica", font_size)
        text.setHorizScale(100.0 * line_w / tw if tw > 0 else 100.0)
        text.setTextOrigin(x0, H - y1)
        text.textOut(s)
    c.drawText(text)
    c.save()


def write_layout(page_pdfs, out_path: Path):
    """Surya layout detection on every page image: figures, pictures and tables
    with bounding boxes in page-pixel coordinates. Page numbers are 1-based in
    url order (the order of the merged PDF)."""
    try:
        from surya.layout import LayoutPredictor
        from surya.foundation import FoundationPredictor
    except ImportError as e:
        print(f"layout skipped: {e}")
        return
    try:
        predictor = LayoutPredictor(FoundationPredictor())
    except TypeError:
        predictor = LayoutPredictor()
    out = []
    wanted = {"figure", "picture", "table", "image", "plate"}
    for i, (sid, jpg, _) in enumerate(page_pdfs, 1):
        try:
            img = Image.open(jpg).convert("RGB")
            res = predictor([img])[0]
            regions = []
            for b in getattr(res, "bboxes", []):
                label = str(getattr(b, "label", "")).lower()
                if label in wanted:
                    regions.append({"label": label, "bbox": [float(x) for x in b.bbox]})
            out.append({"page": i, "id": sid, "width": img.width, "height": img.height, "regions": regions})
        except Exception as e:
            print(f"  layout {sid}: {e}")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"layout: {sum(len(p['regions']) for p in out)} figure/table regions on {len(out)} pages -> {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="?", default="urls.txt")
    ap.add_argument("--images-dir", default="nb_output")
    ap.add_argument("--out", default="book.pdf")
    ap.add_argument("--keep-images", action="store_true",
                    help="keep page JPGs and per-page PDFs after merging "
                         "(default: delete them; the merged PDF is the artefact)")
    ap.add_argument("--no-merge", action="store_true",
                    help="OCR pages but don't build final merged PDF")
    ap.add_argument("--force", action="store_true",
                    help="re-OCR pages whose per-page PDF already exists")
    ap.add_argument("--batch", type=int, default=8,
                    help="pages per Surya call (default 8; raise if VRAM allows)")
    ap.add_argument("--rec-bs", type=int, default=64,
                    help="Surya recognition batch size (lines/step; lower if OOM)")
    ap.add_argument("--det-bs", type=int, default=4,
                    help="Surya detection batch size (images/step; lower if OOM)")
    ap.add_argument("--layout", action="store_true",
                    help="also run Surya layout detection and write layout.json next to "
                         "--out: per page the Figure/Picture/Table regions with bounding "
                         "boxes, for harvest-claims/scripts/find_figures.py")
    args = ap.parse_args()

    urls_file = Path(args.urls)
    if not urls_file.exists():
        sys.exit(f"missing {urls_file}")
    raw = [u.strip() for u in urls_file.read_text().splitlines()
           if u.strip() and not u.strip().startswith("#")]
    urls = [u for line in raw for u in expand_range(line)]
    print(f"Loaded {len(urls)} pages")

    images_dir = Path(args.images_dir)
    pdf_dir = images_dir / "_searchable"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    page_pdfs, missing, todo = [], [], []
    for url in urls:
        sid = safe_id(url)
        jpg = images_dir / f"{sid}.jpg"
        page_pdf = pdf_dir / f"{sid}.pdf"
        if not jpg.exists():
            missing.append(sid)
            continue
        page_pdfs.append((sid, jpg, page_pdf))
        if args.force or not page_pdf.exists():
            todo.append((sid, jpg, page_pdf))

    if missing:
        print(f"WARNING: {len(missing)} images missing in {images_dir}: "
              f"{missing[:5]}{'...' if len(missing) > 5 else ''}")

    if todo:
        import time
        import torch
        print(f"OCR queue: {len(todo)} pages "
              f"({len(page_pdfs) - len(todo)} already done)")
        print("Loading Surya models (one-time, ~30s)...")
        rec, det = init_surya()
        bs = max(1, args.batch)
        done = 0
        for start in range(0, len(todo), bs):
            chunk = todo[start:start + bs]
            paths = [c[1] for c in chunk]
            t0 = time.time()
            try:
                preds = ocr_batch(rec, det, paths, args.rec_bs, args.det_bs)
            except torch.cuda.OutOfMemoryError as e:
                print(f"  [batch {start+1}..{start+len(chunk)}] OOM — "
                      f"falling back to 1-at-a-time")
                torch.cuda.empty_cache()
                preds = []
                for p in paths:
                    try:
                        preds.extend(ocr_batch(rec, det, [p],
                                               max(16, args.rec_bs // 4), 1))
                    except Exception as e2:
                        print(f"    {p.name}: still FAIL — {e2}")
                        preds.append(None)
                        torch.cuda.empty_cache()
            except Exception as e:
                print(f"  [batch {start+1}..{start+len(chunk)}/{len(todo)}] FAIL — {e}")
                continue
            for (sid, jpg, page_pdf), pred in zip(chunk, preds):
                if pred is None:
                    continue
                try:
                    make_page_pdf(jpg, pred.text_lines, page_pdf)
                except Exception as e:
                    print(f"    {sid}: PDF build FAIL — {e}")
            done += len(chunk)
            dt = time.time() - t0
            print(f"  [{done}/{len(todo)}] batch of {len(chunk)} in {dt:.1f}s "
                  f"({dt/len(chunk):.2f}s/page)")
    else:
        print("Nothing to OCR.")

    if args.layout:
        write_layout(page_pdfs, Path(args.out).with_name("layout.json"))

    if args.no_merge:
        return

    have = [(sid, p) for sid, _, p in page_pdfs if p.exists()]
    print(f"Merging {len(have)} pages -> {args.out}")
    out = pikepdf.Pdf.new()
    for _, p in have:
        with pikepdf.open(p) as src:
            out.pages.extend(src.pages)
    out.save(args.out)
    print(f"Done: {args.out}")

    if args.keep_images:
        return
    # The merged PDF embeds the originals, so the intermediates are dead weight
    # (a 241-page book leaves ~1 GB behind). Only files this run knows about.
    for _, jpg, page_pdf in page_pdfs:
        jpg.unlink(missing_ok=True)
        page_pdf.unlink(missing_ok=True)
    for d in (pdf_dir, images_dir):
        if d.exists() and not any(d.iterdir()):
            d.rmdir()
    print(f"Cleaned up page images in {images_dir}")


if __name__ == "__main__":
    main()
