#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak,
    Preformatted, Table, TableStyle, KeepTogether, Flowable, HRFlowable,
    Image as PDFImage, NextPageTemplate,
)
from reportlab.lib.utils import ImageReader
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Circle

NAVY = colors.HexColor("#12324B")
NAVY2 = colors.HexColor("#0B2133")
BLUE = colors.HexColor("#1769AA")
CYAN = colors.HexColor("#00A6C8")
TEAL = colors.HexColor("#2E7D78")
GREEN = colors.HexColor("#2F7D4B")
AMBER = colors.HexColor("#B56A00")
RED = colors.HexColor("#B3322B")
INK = colors.HexColor("#1D2A35")
MUTED = colors.HexColor("#5D6C78")
LIGHT = colors.HexColor("#F4F7FA")
LIGHT_BLUE = colors.HexColor("#EAF3F9")
LIGHT_TEAL = colors.HexColor("#EAF7F5")
LIGHT_AMBER = colors.HexColor("#FFF6E8")
LIGHT_RED = colors.HexColor("#FCEDEC")
BORDER = colors.HexColor("#D6DEE5")
WHITE = colors.white
CODE_FENCE = chr(96) * 3
MANUAL_META = {"revision": "unknown", "date": "undated", "stable": "uncontrolled"}


def register_fonts():
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
         "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
    ]
    for regular, bold, mono in candidates:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("CX", regular))
            pdfmetrics.registerFont(TTFont("CX-Bold", bold))
            if Path(mono).exists():
                pdfmetrics.registerFont(TTFont("CX-Mono", mono))
                return "CX", "CX-Bold", "CX-Mono"
            return "CX", "CX-Bold", "Courier"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONT, FONT_BOLD, FONT_MONO = register_fonts()


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\x60([^\x60]+)\x60", lambda m: f'<font name="{FONT_MONO}">{m.group(1)}</font>', text)
    text = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<link href="\2" color="#1769AA"><u>\1</u></link>', text)
    return text


BASE = getSampleStyleSheet()
ST = {
    "H1": ParagraphStyle("H1", parent=BASE["Heading1"], fontName=FONT_BOLD, fontSize=17, leading=21, textColor=NAVY, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    "H2": ParagraphStyle("H2", parent=BASE["Heading2"], fontName=FONT_BOLD, fontSize=13, leading=17, textColor=BLUE, spaceBefore=9, spaceAfter=5, keepWithNext=True),
    "H3": ParagraphStyle("H3", parent=BASE["Heading3"], fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=INK, spaceBefore=7, spaceAfter=4, keepWithNext=True),
    "Body": ParagraphStyle("Body", parent=BASE["BodyText"], fontName=FONT, fontSize=9, leading=13, textColor=INK, spaceAfter=5),
    "Bullet": ParagraphStyle("Bullet", parent=BASE["BodyText"], fontName=FONT, fontSize=8.9, leading=12.6, leftIndent=11, firstLineIndent=-6, textColor=INK, spaceAfter=3),
    "Number": ParagraphStyle("Number", parent=BASE["BodyText"], fontName=FONT, fontSize=8.9, leading=12.6, leftIndent=12, firstLineIndent=-9, textColor=INK, spaceAfter=3),
    "Code": ParagraphStyle("Code", parent=BASE["Code"], fontName=FONT_MONO, fontSize=7.2, leading=9.5, leftIndent=4, rightIndent=4, borderColor=BORDER, borderWidth=.5, borderPadding=6, backColor=colors.HexColor("#F7F9FB"), textColor=INK, spaceBefore=4, spaceAfter=7),
    "Table": ParagraphStyle("Table", parent=BASE["BodyText"], fontName=FONT, fontSize=7.5, leading=9.6, textColor=INK),
    "TableHead": ParagraphStyle("TableHead", parent=BASE["BodyText"], fontName=FONT_BOLD, fontSize=7.5, leading=9.6, textColor=WHITE),
    "CalloutTitle": ParagraphStyle("CalloutTitle", parent=BASE["BodyText"], fontName=FONT_BOLD, fontSize=9, leading=12, textColor=INK, spaceAfter=2),
    "CalloutBody": ParagraphStyle("CalloutBody", parent=BASE["BodyText"], fontName=FONT, fontSize=8.5, leading=12, textColor=INK),
    "TOCHead": ParagraphStyle("TOCHead", parent=BASE["Heading1"], fontName=FONT_BOLD, fontSize=20, leading=24, textColor=NAVY, spaceAfter=10),
    "TOC0": ParagraphStyle("TOC0", parent=BASE["BodyText"], fontName=FONT_BOLD, fontSize=9, leading=12.2, textColor=NAVY, spaceBefore=4, spaceAfter=2),
    "TOC1": ParagraphStyle("TOC1", parent=BASE["BodyText"], fontName=FONT, fontSize=8.2, leading=11.2, textColor=INK, leftIndent=12, spaceAfter=2),
    "Caption": ParagraphStyle("Caption", parent=BASE["BodyText"], fontName=FONT, fontSize=7.5, leading=10, textColor=MUTED, alignment=1, spaceAfter=6),
}


class ManualDoc(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        self.current_chapter = "Front Matter"
        self._seq = 0
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        wide_width, wide_height = landscape(A4)
        screenshot_frame = Frame(
            14 * mm,
            17 * mm,
            wide_width - 28 * mm,
            wide_height - 31 * mm,
            id="gui_screenshots",
        )
        self.addPageTemplates([
            PageTemplate(id="main", frames=frame, onPage=self.page_decor, pagesize=A4),
            PageTemplate(
                id="gui_screenshots",
                frames=screenshot_frame,
                onPage=self.page_decor,
                pagesize=landscape(A4),
            ),
        ])

    def beforeDocument(self):
        # multiBuild performs more than one layout pass for the table of
        # contents. Reset page-header context so the cover/TOC does not inherit
        # the last chapter title from the preceding pass.
        self.current_chapter = "Controlled manual"

    def page_decor(self, canvas, doc):
        canvas.saveState()
        w, h = canvas._pagesize
        canvas.setFillColor(NAVY2)
        canvas.rect(0, h-13*mm, w, 13*mm, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont(FONT_BOLD, 7.4)
        canvas.drawString(16*mm, h-8.3*mm, "CLEANROOMX | PROFESSIONAL ENGINEERING USER MANUAL")
        canvas.setFont(FONT, 7)
        canvas.drawRightString(
            w-16*mm,
            h-8.3*mm,
            f"REVISION {MANUAL_META.get('revision', 'unknown')}",
        )
        canvas.setStrokeColor(BORDER)
        canvas.line(16*mm, 14*mm, w-16*mm, 14*mm)
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 7)
        revision = MANUAL_META.get("revision", "unknown")
        issue_date = MANUAL_META.get("date", "undated")
        stable = MANUAL_META.get("stable", "uncontrolled")
        canvas.drawString(16*mm, 9.2*mm, f"Revision {revision} | {issue_date} | Stable baseline {stable}")
        canvas.drawRightString(w-16*mm, 9.2*mm, f"Page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("H1", "H2"):
            text = flowable.getPlainText()
            level = 0 if flowable.style.name == "H1" else 1
            if level == 0:
                self.current_chapter = text
            key = getattr(flowable, "_cx_key", None)
            if key is None:
                self._seq += 1
                key = f"h{self._seq}"
                setattr(flowable, "_cx_key", key)
            self.canv.bookmarkPage(key)
            try:
                self.canv.addOutlineEntry(text, key, level=level, closed=False)
            except Exception:
                pass
            self.notify("TOCEntry", (level, text, self.page, key))


class ChapterBanner(Flowable):
    def __init__(self, number, title):
        super().__init__()
        self.number = number
        self.title = title
        self.height = 51*mm

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return availWidth, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.roundRect(0, 0, self.width, self.height, 4*mm, fill=1, stroke=0)
        c.setFillColor(CYAN)
        c.rect(0, self.height-6*mm, self.width, 6*mm, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont(FONT_BOLD, 10.5)
        c.drawString(11*mm, self.height-18*mm, f"CHAPTER {self.number}")
        words = self.title.split()
        lines, line = [], ""
        for word in words:
            test = (line + " " + word).strip()
            if c.stringWidth(test, FONT_BOLD, 20) > self.width-22*mm and line:
                lines.append(line)
                line = word
            else:
                line = test
        if line:
            lines.append(line)
        c.setFont(FONT_BOLD, 20)
        y = self.height-31*mm
        for ln in lines[:2]:
            c.drawString(11*mm, y, ln)
            y -= 7.5*mm


def callout(kind, title, body):
    palette = {
        "NOTE": (BLUE, LIGHT_BLUE),
        "TIP": (TEAL, LIGHT_TEAL),
        "QUALITY": (GREEN, colors.HexColor("#EAF5ED")),
        "WARNING": (AMBER, LIGHT_AMBER),
        "CRITICAL": (RED, LIGHT_RED),
    }
    accent, bg = palette.get(kind, (BLUE, LIGHT_BLUE))
    t = Table([
        ["", Paragraph(inline(title), ST["CalloutTitle"])],
        ["", Paragraph(inline(body), ST["CalloutBody"])],
    ], colWidths=[3*mm, 165*mm], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("BACKGROUND", (0,0), (0,-1), accent),
        ("SPAN", (0,0), (0,-1)),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (1,0), (-1,-1), 7),
        ("RIGHTPADDING", (1,0), (-1,-1), 7),
        ("TOPPADDING", (1,0), (-1,0), 6),
        ("BOTTOMPADDING", (1,-1), (-1,-1), 7),
        ("BOX", (0,0), (-1,-1), .5, BORDER),
    ]))
    return KeepTogether([t, Spacer(1,3)])


GUI_SCREENSHOT_FILES = {
    "start-center.png": "Start Center and project actions",
    "design-2d.png": "2D floor plan and room editing",
    "design-3d.png": "3D room view",
    "design-split.png": "Synchronized 2D and 3D design",
    "input-structured.png": "Structured project inputs",
    "input-json-editor.png": "Strict JSON input editor",
    "plot.png": "Analysis plot workspace",
    "proofgraph.png": "ProofGraph evidence explorer",
    "openfoam.png": "OpenFOAM case and evidence workbench",
    "output-problems.png": "Problems output panel",
    "output-diagnostics.png": "Diagnostics output panel",
    "output-verification.png": "Verification output panel",
    "output-console.png": "Console output panel",
    "output-evidence.png": "Evidence output panel",
    "output-results.png": "Results output panel",
    "output-report.png": "Report output panel",
}


def _load_gui_screenshot_records(source_path: Path, preview_snapshot: str):
    screenshot_dir = source_path.parent / "gui_screenshots"
    manifest_path = screenshot_dir / "capture-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"GUI screenshot manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("captures"), list):
        raise ValueError("GUI screenshot manifest must contain a captures array")
    if manifest.get("errors"):
        raise ValueError("GUI screenshot manifest records capture errors")
    expected_commit = re.search(r"@\s*([0-9a-f]{7,40})", preview_snapshot or "")
    actual_commit = manifest.get("source_commit")
    if not expected_commit or not isinstance(actual_commit, str):
        raise ValueError("GUI screenshot commit cannot be matched to the manual preview")
    if not actual_commit.lower().startswith(expected_commit.group(1).lower()):
        raise ValueError("GUI screenshots were captured from a different source commit")

    captures_by_name = {}
    for item in manifest["captures"]:
        if not isinstance(item, dict):
            raise ValueError("GUI screenshot capture entries must be objects")
        filename = item.get("file")
        if filename not in GUI_SCREENSHOT_FILES and filename != "openfoam-timeseries.png":
            raise ValueError(f"Unexpected GUI screenshot filename: {filename!r}")
        if filename in captures_by_name:
            raise ValueError(f"Duplicate GUI screenshot entry: {filename}")
        captures_by_name[filename] = item
    required = set(GUI_SCREENSHOT_FILES)
    if not required.issubset(captures_by_name):
        missing = sorted(required.difference(captures_by_name))
        raise ValueError(f"GUI screenshot set is incomplete: {', '.join(missing)}")

    records = []
    for filename, item in captures_by_name.items():
        path = screenshot_dir / filename
        if path.is_symlink() or not path.is_file() or path.resolve().parent != screenshot_dir.resolve():
            raise ValueError(f"GUI screenshot is missing or unsafe: {filename}")
        try:
            actual_size = ImageReader(str(path)).getSize()
        except Exception as exc:
            raise ValueError(f"GUI screenshot is not a readable image: {filename}") from exc
        dimensions = item.get("dimensions_px")
        if (
            not isinstance(dimensions, list)
            or len(dimensions) != 2
            or not isinstance(dimensions[0], int)
            or not isinstance(dimensions[1], int)
            or dimensions[0] < 700
            or dimensions[1] < 500
            or tuple(dimensions) != actual_size
        ):
            raise ValueError(f"GUI screenshot dimensions are invalid: {filename}")
        label = GUI_SCREENSHOT_FILES.get(filename, "OpenFOAM mapped-field time-series dialog")
        records.append((filename, label, path, dimensions))
    return records


def add_gui_screenshot_gallery(story, source_path: Path, preview_snapshot: str):
    records = _load_gui_screenshot_records(source_path, preview_snapshot)
    if records is None:
        story.append(callout(
            "WARNING",
            "Real GUI screenshots are not attached to this manual build",
            "Capture the 16-view CleanroomX screenshot set on a desktop with "
            "`python scripts/capture_gui_screenshots.py`, then rebuild this manual. "
            "A mapped-field time-series screen can be added from a real result store "
            "with `--timeseries-result-directory`. No substitute or synthetic UI "
            "images are inserted.",
        ))
        return

    wide_width, wide_height = landscape(A4)
    image_width = wide_width - 28 * mm
    image_height = wide_height - 55 * mm
    story.append(NextPageTemplate("gui_screenshots"))
    story.append(PageBreak())
    for index, (filename, label, path, dimensions) in enumerate(records, start=1):
        title = f"{index:02d}. {label}"
        image = PDFImage(str(path), width=image_width, height=image_height, kind="proportional")
        image.hAlign = "CENTER"
        story.append(Paragraph(inline(title), ST["H2"]))
        story.append(image)
        story.append(Paragraph(
            inline(f"{filename} | {dimensions[0]} × {dimensions[1]} px | "
                   f"Source commit {preview_snapshot.split('@', 1)[-1].strip().split()[0]}"),
            ST["Caption"],
        ))
        if index < len(records):
            story.append(PageBreak())
    story.extend([NextPageTemplate("main"), PageBreak()])


def md_table(lines, width):
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) > 1 and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in rows[1]):
        rows.pop(1)
    n = max(len(r) for r in rows)
    rows = [r + [""]*(n-len(r)) for r in rows]
    data = []
    for ri, row in enumerate(rows):
        style = ST["TableHead"] if ri == 0 else ST["Table"]
        data.append([Paragraph(inline(c), style) for c in row])
    if n == 2:
        widths = [width*.32, width*.68]
    elif n == 3:
        widths = [width*.24, width*.34, width*.42]
    elif n == 4:
        widths = [width*.18, width*.22, width*.28, width*.32]
    else:
        widths = [width/n]*n
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("GRID", (0,0), (-1,-1), .35, BORDER),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT]),
    ]))
    return t


def architecture(width=170*mm, height=88*mm):
    d = Drawing(width, height)
    layers = [
        ("Operator surfaces", "GUI | 2D/3D | CLI | Batch", colors.HexColor("#EAF5F7")),
        ("Application service", "Registry | Parse | Run | Report", colors.HexColor("#EDF3FA")),
        ("Engineering services", "Verification | HVAC | Networks | Uncertainty", colors.HexColor("#EDF7EF")),
        ("Assurance & evidence", "Consistency | Compliance | ProofGraph", colors.HexColor("#FFF6E8")),
        ("Project lifecycle", "Persistence | Recovery | History | Bundles", colors.HexColor("#F6EFF8")),
        ("External inputs", "Requirements | IFC | Manufacturer data | Measurements", colors.HexColor("#F2F3F5")),
    ]
    box_h, gap = 11*mm, 3*mm
    y = height-box_h-4*mm
    for i,(title,desc,bg) in enumerate(layers):
        d.add(Rect(2*mm,y,width-4*mm,box_h,2*mm,2*mm,fillColor=bg,strokeColor=colors.HexColor("#AAB9C4"),strokeWidth=.7))
        d.add(String(8*mm,y+6.4*mm,title,fontName=FONT_BOLD,fontSize=8.5,fillColor=NAVY))
        d.add(String(58*mm,y+6.4*mm,desc,fontName=FONT,fontSize=7.4,fillColor=INK))
        if i < len(layers)-1:
            x = width/2
            d.add(Line(x,y-1*mm,x,y-gap+.5*mm,strokeColor=MUTED,strokeWidth=.8))
            d.add(Polygon([x-1.4*mm,y-gap+1.5*mm,x+1.4*mm,y-gap+1.5*mm,x,y-gap],fillColor=MUTED,strokeColor=MUTED))
        y -= box_h+gap
    return d


def lifecycle(width=170*mm, height=46*mm):
    d = Drawing(width, height)
    steps = [("1","Requirements"),("2","Model"),("3","Validate"),("4","Run"),("5","Review"),("6","Evidence"),("7","Handoff")]
    x0, y, bw, bh, gap = 5*mm, 18*mm, 20*mm, 14*mm, 3.3*mm
    for i,(n,label) in enumerate(steps):
        x = x0+i*(bw+gap)
        fill = LIGHT_BLUE if i < 3 else (LIGHT_TEAL if i < 5 else LIGHT_AMBER)
        d.add(Rect(x,y,bw,bh,2*mm,2*mm,fillColor=fill,strokeColor=colors.HexColor("#AAB9C4"),strokeWidth=.6))
        d.add(Circle(x+4*mm,y+bh-4*mm,2.4*mm,fillColor=NAVY,strokeColor=NAVY))
        d.add(String(x+3.2*mm,y+bh-5.1*mm,n,fontName=FONT_BOLD,fontSize=6,fillColor=WHITE))
        d.add(String(x+3*mm,y+5*mm,label,fontName=FONT_BOLD,fontSize=6.8,fillColor=INK))
        if i < len(steps)-1:
            x2 = x+bw+gap-.8*mm
            d.add(Line(x+bw+.5*mm,y+bh/2,x2,y+bh/2,strokeColor=MUTED,strokeWidth=.8))
            d.add(Polygon([x2-1.3*mm,y+bh/2+1.2*mm,x2-1.3*mm,y+bh/2-1.2*mm,x2,y+bh/2],fillColor=MUTED,strokeColor=MUTED))
    return d


def sync(width=170*mm, height=55*mm):
    d = Drawing(width, height)
    lx, rx, y, bw, bh = 8*mm, 105*mm, 20*mm, 55*mm, 24*mm
    d.add(Rect(lx,y,bw,bh,2*mm,2*mm,fillColor=LIGHT_BLUE,strokeColor=BLUE,strokeWidth=.8))
    d.add(String(lx+5*mm,y+15*mm,"Spatial model",fontName=FONT_BOLD,fontSize=9,fillColor=NAVY))
    d.add(String(lx+5*mm,y+9*mm,"X/Y + dimensions + devices",fontName=FONT,fontSize=7.2,fillColor=INK))
    d.add(Rect(rx,y,bw,bh,2*mm,2*mm,fillColor=LIGHT_TEAL,strokeColor=TEAL,strokeWidth=.8))
    d.add(String(rx+5*mm,y+15*mm,"Engineering input",fontName=FONT_BOLD,fontSize=9,fillColor=NAVY))
    d.add(String(rx+5*mm,y+9*mm,"Dimensions + criteria + evidence",fontName=FONT,fontSize=7.2,fillColor=INK))
    y1 = y+17*mm
    d.add(Line(lx+bw+5*mm,y1,rx-5*mm,y1,strokeColor=BLUE,strokeWidth=1.1))
    d.add(Polygon([rx-6.5*mm,y1+1.5*mm,rx-6.5*mm,y1-1.5*mm,rx-5*mm,y1],fillColor=BLUE,strokeColor=BLUE))
    d.add(String(70*mm,y1+2.5*mm,"Push dimensions only",fontName=FONT_BOLD,fontSize=6.8,fillColor=BLUE))
    y2 = y+7*mm
    d.add(Line(rx-5*mm,y2,lx+bw+5*mm,y2,strokeColor=TEAL,strokeWidth=1.1))
    d.add(Polygon([lx+bw+6.5*mm,y2+1.5*mm,lx+bw+6.5*mm,y2-1.5*mm,lx+bw+5*mm,y2],fillColor=TEAL,strokeColor=TEAL))
    d.add(String(72*mm,y2+2.5*mm,"Pull dimensions only",fontName=FONT_BOLD,fontSize=6.8,fillColor=TEAL))
    return d


def evidence(width=170*mm, height=52*mm):
    d = Drawing(width, height)
    labels = ["Requirement","Input evidence","Canonical analysis","Finding","Verdict","Report / snapshot"]
    fills = [LIGHT_AMBER,LIGHT_BLUE,LIGHT_TEAL,colors.HexColor("#F0F6EA"),colors.HexColor("#F6EFF8"),LIGHT]
    x, y, bw, gap, bh = 4*mm, 17*mm, 24*mm, 4*mm, 17*mm
    for i,label in enumerate(labels):
        d.add(Rect(x,y,bw,bh,2*mm,2*mm,fillColor=fills[i],strokeColor=colors.HexColor("#AAB9C4"),strokeWidth=.6))
        words = label.split()
        d.add(String(x+4*mm,y+(10 if len(words)>1 else 7)*mm,words[0],fontName=FONT_BOLD,fontSize=6.6,fillColor=NAVY))
        if len(words)>1:
            d.add(String(x+4*mm,y+5*mm," ".join(words[1:]),fontName=FONT_BOLD,fontSize=6.6,fillColor=NAVY))
        if i < len(labels)-1:
            x2 = x+bw+gap-1*mm
            d.add(Line(x+bw+1*mm,y+bh/2,x2,y+bh/2,strokeColor=MUTED,strokeWidth=.8))
            d.add(Polygon([x2-1.2*mm,y+bh/2+1.2*mm,x2-1.2*mm,y+bh/2-1.2*mm,x2,y+bh/2],fillColor=MUTED,strokeColor=MUTED))
        x += bw+gap
    return d


def pressure(width=170*mm, height=58*mm):
    d = Drawing(width, height)
    nodes = [("Process",25*mm,NAVY),("Airlock",82*mm,BLUE),("Corridor / ref",140*mm,TEAL)]
    y = 30*mm
    for label,x,col in nodes:
        d.add(Circle(x,y,9*mm,fillColor=WHITE,strokeColor=col,strokeWidth=1.4))
        d.add(String(x-7*mm,y+1*mm,label,fontName=FONT_BOLD,fontSize=6.8,fillColor=INK))
    d.add(Line(34*mm,y,73*mm,y,strokeColor=MUTED,strokeWidth=1.2))
    d.add(Polygon([71*mm,y+1.5*mm,71*mm,y-1.5*mm,73*mm,y],fillColor=MUTED,strokeColor=MUTED))
    d.add(Line(91*mm,y,131*mm,y,strokeColor=MUTED,strokeWidth=1.2))
    d.add(Polygon([129*mm,y+1.5*mm,129*mm,y-1.5*mm,131*mm,y],fillColor=MUTED,strokeColor=MUTED))
    return d


def deployment(width=170*mm, height=62*mm):
    d = Drawing(width, height)
    cols = [
        ("Controlled workstation", ["Pinned CleanroomX build","Normal user privileges","Project workspace"], 8*mm, LIGHT_BLUE),
        ("Engineering review", ["Independent review","Diagnostics","Freshness + assumptions"], 64*mm, LIGHT_TEAL),
        ("Controlled records", ["Project bundle","HTML/PDF report","Snapshot + test evidence"], 120*mm, LIGHT_AMBER),
    ]
    for title,body,x,bg in cols:
        d.add(Rect(x,17*mm,46*mm,30*mm,2*mm,2*mm,fillColor=bg,strokeColor=colors.HexColor("#AAB9C4"),strokeWidth=.7))
        d.add(String(x+4*mm,39*mm,title,fontName=FONT_BOLD,fontSize=7.5,fillColor=NAVY))
        for j,line in enumerate(body):
            d.add(String(x+4*mm,32*mm-j*6*mm,line,fontName=FONT,fontSize=6.8,fillColor=INK))
    for x in [54*mm,110*mm]:
        d.add(Line(x,32*mm,x+8*mm,32*mm,strokeColor=MUTED,strokeWidth=.9))
        d.add(Polygon([x+6*mm,33.5*mm,x+6*mm,30.5*mm,x+8*mm,32*mm],fillColor=MUTED,strokeColor=MUTED))
    return d


DIAGRAMS = {"architecture":architecture,"lifecycle":lifecycle,"sync":sync,"evidence":evidence,"pressure":pressure,"deployment":deployment}


def front_matter(lines):
    meta = {}
    if not lines or lines[0].strip() != "---":
        return meta, lines
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        if ":" in lines[i]:
            k,v = lines[i].split(":",1)
            meta[k.strip()] = v.strip()
        i += 1
    return meta, lines[i+1:]


def cover(meta):
    usable = A4[0]-34*mm
    rows = [
        ["Document","Engineering User & Validation Manual"],
        ["Revision",meta.get("revision","unknown")],
        ["Stable release",meta.get("stable","uncontrolled")],
        ["Engineering baseline",meta.get("baseline","")],
        ["Preview snapshot",meta.get("preview_snapshot","not applicable")],
        ["Manual date",meta.get("date","undated")],
    ]
    data = [[Paragraph(inline(a),ST["TableHead"] if i==0 else ST["Table"]),Paragraph(inline(b),ST["TableHead"] if i==0 else ST["Table"])] for i,(a,b) in enumerate(rows)]
    t = Table(data,colWidths=[44*mm,116*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),NAVY2),("BACKGROUND",(0,1),(0,-1),LIGHT_BLUE),
        ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#9AB0C0")),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)
    ]))
    title = ParagraphStyle("CoverTitle", parent=BASE["Title"], fontName=FONT_BOLD, fontSize=25, leading=30, textColor=WHITE, alignment=0)
    sub = ParagraphStyle("CoverSub", parent=BASE["BodyText"], fontName=FONT, fontSize=11.2, leading=16, textColor=colors.HexColor("#DCEAF3"))
    return [
        Spacer(1,12*mm),
        Table([[Paragraph("CLEANROOMX",ParagraphStyle("Brand",fontName=FONT_BOLD,fontSize=16,textColor=CYAN))]],colWidths=[usable],style=[("BACKGROUND",(0,0),(-1,-1),NAVY2),("LEFTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]),
        Table([[Paragraph("Engineering User & Validation Manual",title)],[Paragraph("Design • Simulation • HVAC • Networks • BIM/IFC • Verification • Evidence • Controlled Handoff",sub)]],colWidths=[usable],style=[("BACKGROUND",(0,0),(-1,-1),NAVY),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)]),
        Spacer(1,10*mm),t,Spacer(1,7*mm),
        callout("CRITICAL","Engineering and regulatory boundary","CleanroomX provides engineering screening, simulation, verification, and software/provenance evidence. It does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance. Applicable criteria remain explicit project inputs and require qualified review."),
        Spacer(1,8*mm),
        Paragraph("Intended audience: cleanroom/HVAC engineers, BIM coordinators, verification engineers, reviewers, QA/validation personnel, technical leads, and controlled-document owners.",ST["Body"]),
        Paragraph("This revision expands the desktop operating procedure and identifies which features belong to the stable release and which belong to the documented development preview.",ST["Body"]),
        PageBreak()
    ]


def parse(source):
    source_path = Path(source).resolve()
    lines = source_path.read_text(encoding="utf-8").splitlines()
    meta, lines = front_matter(lines)
    MANUAL_META.clear()
    MANUAL_META.update(meta)
    story = cover(meta)
    story.append(Paragraph("Contents",ST["TOCHead"]))
    toc = TableOfContents()
    toc.levelStyles = [ST["TOC0"],ST["TOC1"]]
    toc.dotsMinLevel = 0
    story += [toc,PageBreak()]
    usable = A4[0]-34*mm
    para, i = [], 0

    def flush():
        nonlocal para
        if para:
            value = " ".join(x.strip() for x in para).strip()
            if value:
                story.append(Paragraph(inline(value),ST["Body"]))
            para = []

    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            flush(); i += 1; continue
        m = re.fullmatch(r"\[DIAGRAM:([a-z_]+)(?:\|([^\]]+))?\]",s)
        if m:
            flush()
            fn = DIAGRAMS.get(m.group(1))
            if fn:
                story.append(fn())
                if m.group(2):
                    story.append(Paragraph(inline(m.group(2)),ST["Caption"]))
            i += 1; continue
        if s.startswith("> [!"):
            flush()
            cm = re.match(r"> \[!(NOTE|TIP|QUALITY|WARNING|CRITICAL)\]\s*(.*)",s)
            kind = cm.group(1) if cm else "NOTE"
            title = cm.group(2).strip() if cm else kind.title()
            body = []
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                body.append(lines[i].lstrip()[1:].strip())
                i += 1
            story.append(callout(kind,title or kind.title()," ".join(body)))
            continue
        if s.startswith(CODE_FENCE):
            flush(); i += 1; code = []
            while i < len(lines) and not lines[i].strip().startswith(CODE_FENCE):
                code.append(lines[i]); i += 1
            story.append(Preformatted("\n".join(code),ST["Code"]))
            i += 1; continue
        if s.startswith("|"):
            flush(); tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i].strip()); i += 1
            story.append(md_table(tbl,usable)); story.append(Spacer(1,4)); continue
        if s.startswith("# "):
            flush()
            title = s[2:].strip()
            num = title.split(".",1)[0].strip() if re.match(r"^\d+\.",title) else "—"
            chapter = title.split(".",1)[1].strip() if num != "—" else title
            if story and not isinstance(story[-1],PageBreak):
                story.append(PageBreak())
            story += [ChapterBanner(num,chapter),Spacer(1,4),Paragraph(inline(title),ST["H1"])]
            i += 1; continue
        if s.startswith("## "):
            flush(); story.append(Paragraph(inline(s[3:].strip()),ST["H2"])); i += 1; continue
        if s.startswith("### "):
            flush(); story.append(Paragraph(inline(s[4:].strip()),ST["H3"])); i += 1; continue
        if s == "[GUI_SCREENSHOTS]":
            flush()
            add_gui_screenshot_gallery(story, source_path, meta.get("preview_snapshot", ""))
            i += 1
            continue
        if re.match(r"^[-*] ",s):
            flush(); story.append(Paragraph("• "+inline(s[2:].strip()),ST["Bullet"])); i += 1; continue
        n = re.match(r"^(\d+)\.\s+(.*)",s)
        if n:
            flush(); story.append(Paragraph(f"{n.group(1)}. "+inline(n.group(2)),ST["Number"])); i += 1; continue
        if s == "***":
            flush(); story.append(HRFlowable(width="100%",thickness=.6,color=BORDER,spaceBefore=4,spaceAfter=6)); i += 1; continue
        para.append(line); i += 1
    flush()
    return story


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_solution_manual_pdf.py SOURCE.md OUTPUT.pdf")
    doc = ManualDoc(
        sys.argv[2],pagesize=A4,rightMargin=17*mm,leftMargin=17*mm,topMargin=18*mm,bottomMargin=19*mm,
        title="CleanroomX Engineering User & Validation Manual",author="CleanroomX contributors",
        subject="Professional operating, engineering, assurance, and validation manual for CleanroomX"
    )
    doc.multiBuild(parse(sys.argv[1]))


if __name__ == "__main__":
    main()
