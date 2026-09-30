#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

ACCENT = colors.HexColor("#165DFF")
DARK = colors.HexColor("#182230")
MUTED = colors.HexColor("#5C6675")
LIGHT = colors.HexColor("#F4F7FB")
BORDER = colors.HexColor("#D9E0EA")


def _register_fonts():
    sans = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    sans_bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    mono = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    if sans.exists() and sans_bold.exists():
        pdfmetrics.registerFont(TTFont("CX", str(sans)))
        pdfmetrics.registerFont(TTFont("CX-Bold", str(sans_bold)))
        if mono.exists():
            pdfmetrics.registerFont(TTFont("CX-Mono", str(mono)))
        return "CX", "CX-Bold", "CX-Mono" if mono.exists() else "Courier"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = _register_fonts()


def inline_md(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='" + FONT_MONO + r"'>\1</font>", text)
    return text


def page_decor(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont(FONT, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "CleanroomX Complete Solution Manual • 30 September 2026")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def make_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=FONT_BOLD, fontSize=25, leading=30, textColor=DARK, alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", parent=base["BodyText"], fontName=FONT, fontSize=11, leading=15, textColor=MUTED, alignment=TA_CENTER, spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=FONT_BOLD, fontSize=17, leading=21, textColor=ACCENT, spaceBefore=13, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=FONT_BOLD, fontSize=13, leading=17, textColor=DARK, spaceBefore=10, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=FONT_BOLD, fontSize=11, leading=14, textColor=DARK, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=FONT, fontSize=9.2, leading=13, textColor=DARK, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName=FONT, fontSize=9.1, leading=12.5, leftIndent=12, firstLineIndent=-7, textColor=DARK, spaceAfter=3),
        "quote": ParagraphStyle("quote", parent=base["BodyText"], fontName=FONT, fontSize=8.9, leading=12.5, leftIndent=9, rightIndent=9, borderColor=BORDER, borderWidth=0.6, borderPadding=7, backColor=LIGHT, textColor=DARK, spaceBefore=4, spaceAfter=7),
        "code": ParagraphStyle("code", parent=base["Code"], fontName=FONT_MONO, fontSize=7.7, leading=10, leftIndent=5, rightIndent=5, borderColor=BORDER, borderWidth=0.5, borderPadding=6, backColor=colors.HexColor("#F8FAFC"), textColor=colors.HexColor("#1F2937"), spaceBefore=4, spaceAfter=7),
        "table": ParagraphStyle("table", parent=base["BodyText"], fontName=FONT, fontSize=7.5, leading=9.5, textColor=DARK),
        "table_head": ParagraphStyle("table_head", parent=base["BodyText"], fontName=FONT_BOLD, fontSize=7.5, leading=9.5, textColor=colors.white),
    }


def parse_table(lines, styles, width):
    rows = []
    for line in lines:
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    if len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1]):
        rows.pop(1)
    columns = max(len(row) for row in rows)
    rows = [row + [""] * (columns - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(rows):
        style = styles["table_head"] if row_index == 0 else styles["table"]
        data.append([Paragraph(inline_md(cell), style) for cell in row])
    table = Table(data, colWidths=[width / columns] * columns, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]))
    return table


def build(source: Path, output: Path):
    styles = make_styles()
    document = SimpleDocTemplate(
        str(output), pagesize=A4,
        rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=19 * mm,
        title="CleanroomX Complete Solution Manual & User Guide",
        author="CleanroomX contributors",
        subject="CleanroomX design, simulation, verification, BIM/IFC and evidence manual",
    )
    usable_width = A4[0] - 36 * mm
    lines = source.read_text(encoding="utf-8").splitlines()
    story = []
    paragraph_lines = []
    title_mode = True
    index = 0

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            value = " ".join(item.strip() for item in paragraph_lines).strip()
            if value:
                story.append(Paragraph(inline_md(value), styles["body"]))
            paragraph_lines = []

    while index < len(lines):
        line = lines[index].rstrip()
        if line.startswith("<!--"):
            flush_paragraph()
            while index < len(lines) and "-->" not in lines[index]:
                index += 1
            index += 1
            continue
        if not line.strip():
            flush_paragraph()
            index += 1
            continue
        if line.startswith("```"):
            flush_paragraph()
            index += 1
            code = []
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            story.append(Preformatted("\n".join(code), styles["code"]))
            index += 1
            continue
        if line.startswith("|"):
            flush_paragraph()
            table_lines = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.append(parse_table(table_lines, styles, usable_width))
            story.append(Spacer(1, 4))
            continue
        if line.startswith("# "):
            flush_paragraph()
            if story:
                story.append(PageBreak())
            story.append(Paragraph(inline_md(line[2:].strip()), styles["h1"]))
            title_mode = False
            index += 1
            continue
        if line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_md(line[3:].strip()), styles["h2"]))
            index += 1
            continue
        if line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_md(line[4:].strip()), styles["h3"]))
            index += 1
            continue
        if line.startswith("> "):
            flush_paragraph()
            quote = []
            while index < len(lines) and lines[index].startswith("> "):
                quote.append(lines[index][2:].strip())
                index += 1
            story.append(Paragraph(inline_md(" ".join(quote)), styles["quote"]))
            continue
        if re.match(r"^[-*] ", line):
            flush_paragraph()
            story.append(Paragraph("• " + inline_md(line[2:].strip()), styles["bullet"]))
            index += 1
            continue
        numbered = re.match(r"^(\d+)\.\s+(.*)", line)
        if numbered:
            flush_paragraph()
            story.append(Paragraph(numbered.group(1) + ". " + inline_md(numbered.group(2)), styles["bullet"]))
            index += 1
            continue
        if title_mode and not story:
            story.append(Spacer(1, 24))
            story.append(Paragraph(inline_md(line), styles["title"]))
            index += 1
            continue
        if title_mode and len(story) < 8:
            story.append(Paragraph(inline_md(line), styles["subtitle"]))
            index += 1
            continue
        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    document.build(story, onFirstPage=page_decor, onLaterPages=page_decor)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_solution_manual_pdf.py SOURCE.md OUTPUT.pdf")
    build(Path(sys.argv[1]), Path(sys.argv[2]))
