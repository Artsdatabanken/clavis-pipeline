#!/usr/bin/env python3
"""Plain text from a Word .docx file, with nothing but the Python standard
library (a .docx is a zip archive of XML).

Usage: docx_to_text.py IN.docx OUT.txt [--page-every N]

Paragraphs become lines; table cells are separated by " | " and rows by line
breaks; explicit page breaks in the document become form feeds (\\f), so the
harvest scripts see pages the way they see them in a PDF. A document without
page breaks is one page; --page-every N inserts a form feed every N paragraphs
so pages.json and the source check can still point at a place in the text.
Footnotes, comments and text boxes outside the main body are not included.
"""
import argparse
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def para_text(p) -> str:
    out = []
    for node in p.iter():
        if node.tag == W + "t" and node.text:
            out.append(node.text)
        elif node.tag == W + "tab":
            out.append("\t")
        elif node.tag in (W + "br", W + "cr"):
            out.append("\f" if node.get(W + "type") == "page" else "\n")
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx"); ap.add_argument("out")
    ap.add_argument("--page-every", type=int, default=0)
    a = ap.parse_args()
    with zipfile.ZipFile(a.docx) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    lines, n = [], 0
    for el in body:
        if el.tag == W + "p":
            if el.find(f".//{W}lastRenderedPageBreak") is not None and lines:
                pass  # rendering hint only; real page breaks are w:br type=page
            lines.append(para_text(el))
        elif el.tag == W + "tbl":
            for tr in el.iter(W + "tr"):
                cells = [" ".join(para_text(p) for p in tc.iter(W + "p")).strip() for tc in tr.iter(W + "tc")]
                lines.append(" | ".join(cells))
        else:
            continue
        n += 1
        if a.page_every and n % a.page_every == 0:
            lines.append("\f")
    text = "\n".join(lines)
    text = re.sub(r"\n*\f\n*", "\f", text)
    open(a.out, "w", encoding="utf-8").write(text)
    print(f"{len(text.split())} words, {text.count(chr(12)) + 1} pages -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
