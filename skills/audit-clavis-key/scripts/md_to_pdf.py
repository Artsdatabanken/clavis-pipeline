#!/usr/bin/env python3
"""Convert Søterotfamilien.decisions.md into a simple, elegant PDF.

Uses markdown-it-py to parse and reportlab Platypus to render. Designed for
expert readers — clean typography, clear hierarchy, no clutter.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, KeepTogether,
    Table, TableStyle, ListFlowable, ListItem, HRFlowable,
)


# --------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------
FONT_PATHS = {
    "Body":         "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Regular.ttf",
    "Body-Italic":  "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Italic.ttf",
    "Body-Bold":    "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Bold.ttf",
    "Body-BoldIt":  "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-BoldItalic.ttf",
    "Sans":         "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Regular.ttf",
    "Sans-Bold":    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "Mono":         "/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf",
}

for name, path in FONT_PATHS.items():
    pdfmetrics.registerFont(TTFont(name, path))

pdfmetrics.registerFontFamily(
    "Body",
    normal="Body", italic="Body-Italic",
    bold="Body-Bold", boldItalic="Body-BoldIt",
)


# --------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------
COLOR_HEAD   = HexColor("#1f4e3a")   # deep botanical green
COLOR_RULE   = HexColor("#a8b9b0")   # muted sage
COLOR_MUTED  = HexColor("#5b6660")
COLOR_BODY   = HexColor("#1f2421")
COLOR_TABLE_BG = HexColor("#f4f6f4")
COLOR_TABLE_HEAD = HexColor("#dce4dd")


# --------------------------------------------------------------------
# Styles
# --------------------------------------------------------------------
S = getSampleStyleSheet()

style_h1 = ParagraphStyle(
    "H1", parent=S["Heading1"],
    fontName="Sans-Bold", fontSize=22, leading=28,
    textColor=COLOR_HEAD, spaceBefore=0, spaceAfter=4,
)
style_subtitle = ParagraphStyle(
    "Sub", parent=S["Normal"],
    fontName="Body-Italic", fontSize=11, leading=15,
    textColor=COLOR_MUTED, spaceBefore=0, spaceAfter=14,
)
style_h2 = ParagraphStyle(
    "H2", parent=S["Heading2"],
    fontName="Sans-Bold", fontSize=14, leading=18,
    textColor=COLOR_HEAD, spaceBefore=18, spaceAfter=4,
    keepWithNext=True,
)
style_h3 = ParagraphStyle(
    "H3", parent=S["Heading3"],
    fontName="Sans-Bold", fontSize=11, leading=15,
    textColor=COLOR_BODY, spaceBefore=10, spaceAfter=2,
    keepWithNext=True,
)
style_body = ParagraphStyle(
    "Body", parent=S["BodyText"],
    fontName="Body", fontSize=10, leading=14.5,
    textColor=COLOR_BODY, alignment=TA_JUSTIFY,
    spaceBefore=0, spaceAfter=6,
)
style_li = ParagraphStyle(
    "ListItem", parent=style_body,
    spaceBefore=0, spaceAfter=2, alignment=TA_LEFT,
)
style_li_sub = ParagraphStyle(
    "ListSub", parent=style_li,
    leftIndent=14,
)
style_th = ParagraphStyle(
    "TH", parent=style_body,
    fontName="Sans-Bold", fontSize=9, leading=12,
    spaceBefore=0, spaceAfter=0, alignment=TA_LEFT,
)
style_td = ParagraphStyle(
    "TD", parent=style_body,
    fontSize=9, leading=12, spaceBefore=0, spaceAfter=0, alignment=TA_LEFT,
)


# --------------------------------------------------------------------
# Inline markdown → reportlab markup
# --------------------------------------------------------------------
def render_inline(tokens) -> str:
    """Convert markdown-it inline children to reportlab paragraph markup."""
    out = []
    for t in tokens:
        if t.type == "text":
            out.append(escape(t.content))
        elif t.type == "softbreak" or t.type == "hardbreak":
            out.append(" ")
        elif t.type == "code_inline":
            out.append(
                f'<font name="Mono" size="9" color="#3c5544">'
                f'{escape(t.content)}'
                f'</font>'
            )
        elif t.type == "strong_open":
            out.append("<b>")
        elif t.type == "strong_close":
            out.append("</b>")
        elif t.type == "em_open":
            out.append("<i>")
        elif t.type == "em_close":
            out.append("</i>")
        elif t.type == "link_open":
            href = next((a[1] for a in t.attrs.items() if a[0] == "href"), "")
            out.append(f'<link href="{escape(href)}" color="#1a4a8a">')
        elif t.type == "link_close":
            out.append("</link>")
        # other inline types ignored
    return "".join(out)


def escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# --------------------------------------------------------------------
# Walk the markdown token stream → flowables
# --------------------------------------------------------------------
def walk(tokens, out):
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.type == "heading_open":
            level = int(t.tag[1:])  # h1..h6
            inline = tokens[i + 1].children or []
            text = render_inline(inline)
            if level == 1:
                out.append(Paragraph(text, style_h1))
                out.append(HRFlowable(
                    width="100%", thickness=0.6, color=COLOR_RULE,
                    spaceBefore=0, spaceAfter=10,
                ))
            elif level == 2:
                out.append(Paragraph(text, style_h2))
                out.append(HRFlowable(
                    width="40%", thickness=0.4, color=COLOR_RULE,
                    spaceBefore=2, spaceAfter=6,
                ))
            elif level == 3:
                out.append(Paragraph(text, style_h3))
            else:
                out.append(Paragraph(text, style_h3))
            i += 3  # heading_open + inline + heading_close
            continue

        if t.type == "paragraph_open":
            inline = tokens[i + 1].children or []
            text = render_inline(inline)
            if text.strip():
                out.append(Paragraph(text, style_body))
            i += 3
            continue

        if t.type == "bullet_list_open" or t.type == "ordered_list_open":
            depth = 0  # always top-level here; nested handled by recursion
            items, consumed = consume_list(tokens, i)
            ordered = (t.type == "ordered_list_open")
            out.append(ListFlowable(
                items, bulletType="1" if ordered else "bullet",
                bulletFontName="Body",
                bulletColor=COLOR_HEAD if ordered else COLOR_MUTED,
                leftIndent=18, bulletIndent=4,
                spaceBefore=2, spaceAfter=8,
            ))
            i = consumed
            continue

        if t.type == "table_open":
            tbl, consumed = consume_table(tokens, i)
            out.append(KeepTogether([Spacer(0, 2), tbl, Spacer(0, 6)]))
            i = consumed
            continue

        if t.type == "hr":
            out.append(HRFlowable(
                width="100%", thickness=0.4, color=COLOR_RULE,
                spaceBefore=8, spaceAfter=8,
            ))
            i += 1
            continue

        if t.type == "fence" or t.type == "code_block":
            text = escape(t.content.rstrip())
            style = ParagraphStyle(
                "code", parent=style_body, fontName="Mono",
                fontSize=8.5, leading=11.5,
                leftIndent=10, backColor=COLOR_TABLE_BG,
                borderPadding=(6, 6, 6, 6),
            )
            out.append(Paragraph(text.replace("\n", "<br/>"), style))
            i += 1
            continue

        i += 1


def consume_list(tokens, start):
    """Consume a bullet/ordered list starting at tokens[start]; return (items, next_index)."""
    items = []
    i = start + 1
    open_type = tokens[start].type
    close_type = open_type.replace("_open", "_close")
    while i < len(tokens) and tokens[i].type != close_type:
        if tokens[i].type == "list_item_open":
            j = i + 1
            content = []
            while tokens[j].type != "list_item_close":
                if tokens[j].type == "paragraph_open":
                    inline = tokens[j + 1].children or []
                    content.append(Paragraph(render_inline(inline), style_li))
                    j += 3
                    continue
                if tokens[j].type in ("bullet_list_open", "ordered_list_open"):
                    nested_items, end = consume_list(tokens, j)
                    nested = ListFlowable(
                        nested_items,
                        bulletType="bullet",
                        bulletFontName="Body",
                        bulletColor=COLOR_MUTED,
                        leftIndent=14, bulletIndent=2,
                        spaceBefore=2, spaceAfter=2,
                    )
                    content.append(nested)
                    j = end
                    continue
                j += 1
            items.append(ListItem(content, leftIndent=18,
                                  bulletColor=COLOR_HEAD,
                                  spaceBefore=0, spaceAfter=0))
            i = j + 1
        else:
            i += 1
    return items, i + 1  # past close_type


def consume_table(tokens, start):
    rows = []
    i = start + 1
    while i < len(tokens) and tokens[i].type != "table_close":
        if tokens[i].type == "tr_open":
            j = i + 1
            row = []
            while tokens[j].type != "tr_close":
                if tokens[j].type in ("th_open", "td_open"):
                    is_th = tokens[j].type == "th_open"
                    inline = tokens[j + 1].children or []
                    text = render_inline(inline)
                    style = style_th if is_th else style_td
                    row.append(Paragraph(text, style))
                    j += 3
                    continue
                j += 1
            rows.append(row)
            i = j + 1
        else:
            i += 1

    # Build table
    if not rows:
        return Spacer(0, 0), i + 1
    n_cols = len(rows[0])
    # column widths
    avail = (A4[0] - 2 * 2 * cm) - 2  # frame width minus padding
    if n_cols == 5:
        col_w = [avail * 0.20, avail * 0.30, avail * 0.10, avail * 0.10, avail * 0.30]
    elif n_cols == 4:
        col_w = [avail * 0.22, avail * 0.32, avail * 0.10, avail * 0.36]
    elif n_cols == 3:
        col_w = [avail * 0.30, avail * 0.40, avail * 0.30]
    elif n_cols == 2:
        col_w = [avail * 0.45, avail * 0.55]
    else:
        col_w = [avail / n_cols] * n_cols

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_TABLE_HEAD),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, COLOR_HEAD),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, COLOR_RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [None, COLOR_TABLE_BG]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl, i + 1


# --------------------------------------------------------------------
# Page header / footer
# --------------------------------------------------------------------
def make_page_decoration(title: str, subtitle: str):
    def draw(canvas, doc):
        canvas.saveState()
        # Footer: page number, centered
        canvas.setFont("Sans", 8.5)
        canvas.setFillColor(COLOR_MUTED)
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"– {doc.page} –")
        # Header: small title at top right (skip page 1)
        if doc.page > 1:
            canvas.setFont("Sans", 8)
            canvas.setFillColor(COLOR_MUTED)
            canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.2 * cm, title)
            canvas.setStrokeColor(COLOR_RULE)
            canvas.setLineWidth(0.3)
            canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
        canvas.restoreState()
    return draw


# --------------------------------------------------------------------
# Build
# --------------------------------------------------------------------
def build(md_path: Path, pdf_path: Path, subtitle: str | None = None):
    text = md_path.read_text(encoding="utf-8")

    # Strip the H1 line; we'll render our own title block
    first_h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = first_h1.group(1).strip() if first_h1 else md_path.stem
    if first_h1:
        text = text[:first_h1.start()] + text[first_h1.end():]

    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": True})
    md.enable("table")

    tokens = md.parse(text)

    flowables = []
    # Title block
    flowables.append(Paragraph(title, style_h1))
    if subtitle:
        flowables.append(Paragraph(subtitle, style_subtitle))
    flowables.append(HRFlowable(
        width="100%", thickness=0.8, color=COLOR_HEAD,
        spaceBefore=0, spaceAfter=14,
    ))

    walk(tokens, flowables)

    # Document
    doc = BaseDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.2 * cm, bottomMargin=2.2 * cm,
        title=title, author="Generert av digitize-clavis-key",
        subject=title,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        leftPadding=0, rightPadding=0,
        topPadding=0, bottomPadding=0,
    )
    template = PageTemplate(
        id="main", frames=[frame],
        onPage=make_page_decoration(title, ""),
    )
    doc.addPageTemplates([template])
    doc.build(flowables)
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    md_path = Path(sys.argv[1])
    pdf_path = Path(sys.argv[2])
    build(md_path, pdf_path, sys.argv[3] if len(sys.argv) > 3 else None)
