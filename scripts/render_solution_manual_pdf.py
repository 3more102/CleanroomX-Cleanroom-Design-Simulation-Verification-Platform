#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

# CleanroomX visual system
NAVY = colors.HexColor('#12314B')
NAVY_2 = colors.HexColor('#1A4565')
TEAL = colors.HexColor('#168A9A')
BLUE = colors.HexColor('#2B6CB0')
INK = colors.HexColor('#1E2936')
MUTED = colors.HexColor('#607080')
LINE = colors.HexColor('#D6DEE7')
PALE = colors.HexColor('#F3F7FA')
PALE_TEAL = colors.HexColor('#EAF6F7')
PALE_BLUE = colors.HexColor('#EDF4FB')
PALE_AMBER = colors.HexColor('#FFF7E6')
PALE_RED = colors.HexColor('#FDEEEE')
AMBER = colors.HexColor('#C07B00')
RED = colors.HexColor('#A83B3B')
GREEN = colors.HexColor('#2F7D5A')
WHITE = colors.white

DOC_ID = 'CRX-UM-001'
REVISION = 'Rev A'
ISSUE_DATE = '30 September 2026'
BASELINE = 'Stable v0.102.1 | documentation snapshot 9a7ab222'


def register_fonts():
    candidates = [
        ('CX', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        ('CX-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('CX-Mono', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'),
    ]
    ok = True
    for name, path in candidates:
        if not Path(path).exists():
            ok = False
            break
    if ok:
        for name, path in candidates:
            pdfmetrics.registerFont(TTFont(name, path))
        return 'CX', 'CX-Bold', 'CX-Mono'
    return 'Helvetica', 'Helvetica-Bold', 'Courier'


FONT, FONT_BOLD, FONT_MONO = register_fonts()


def inline_md(text: str) -> str:
    # Preserve markdown links while escaping all other text.
    links = []
    def link_repl(m):
        links.append((m.group(1), m.group(2)))
        return f'@@LINK{len(links)-1}@@'
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', link_repl, text)
    text = html.escape(text, quote=False)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', rf"<font name='{FONT_MONO}'>\1</font>", text)
    for i, (label, url) in enumerate(links):
        safe_label = html.escape(label, quote=False)
        safe_url = html.escape(url, quote=True)
        text = text.replace(f'@@LINK{i}@@', f"<link href='{safe_url}' color='#2B6CB0'>{safe_label}</link>")
    return text


def get_styles():
    base = getSampleStyleSheet()
    styles = {}
    styles['cover_brand'] = ParagraphStyle(
        'CoverBrand', parent=base['Title'], fontName=FONT_BOLD, fontSize=31,
        leading=34, textColor=WHITE, alignment=TA_LEFT, spaceAfter=4,
    )
    styles['cover_title'] = ParagraphStyle(
        'CoverTitle', parent=base['Title'], fontName=FONT_BOLD, fontSize=22,
        leading=27, textColor=WHITE, alignment=TA_LEFT, spaceAfter=8,
    )
    styles['cover_sub'] = ParagraphStyle(
        'CoverSub', parent=base['BodyText'], fontName=FONT, fontSize=10.2,
        leading=14.5, textColor=colors.HexColor('#D9EBF2'), alignment=TA_LEFT,
    )
    styles['cover_meta'] = ParagraphStyle(
        'CoverMeta', parent=base['BodyText'], fontName=FONT, fontSize=8.8,
        leading=12, textColor=INK,
    )
    styles['part'] = ParagraphStyle(
        'PartHeading', parent=base['Heading1'], fontName=FONT_BOLD, fontSize=18,
        leading=22, textColor=WHITE, alignment=TA_LEFT, spaceAfter=0,
    )
    styles['h1'] = ParagraphStyle(
        'Heading1', parent=base['Heading1'], fontName=FONT_BOLD, fontSize=17,
        leading=21, textColor=NAVY, spaceBefore=0, spaceAfter=7,
    )
    styles['h2'] = ParagraphStyle(
        'Heading2', parent=base['Heading2'], fontName=FONT_BOLD, fontSize=12.3,
        leading=16, textColor=NAVY_2, spaceBefore=10, spaceAfter=5,
        keepWithNext=True,
    )
    styles['h3'] = ParagraphStyle(
        'Heading3', parent=base['Heading3'], fontName=FONT_BOLD, fontSize=10.3,
        leading=13.5, textColor=TEAL, spaceBefore=8, spaceAfter=4,
        keepWithNext=True,
    )
    styles['body'] = ParagraphStyle(
        'Body', parent=base['BodyText'], fontName=FONT, fontSize=8.8,
        leading=12.7, textColor=INK, spaceAfter=5.2,
    )
    styles['small'] = ParagraphStyle(
        'Small', parent=base['BodyText'], fontName=FONT, fontSize=7.6,
        leading=10.4, textColor=MUTED, spaceAfter=3,
    )
    styles['bullet'] = ParagraphStyle(
        'Bullet', parent=styles['body'], leftIndent=12, firstLineIndent=-7,
        spaceAfter=2.8,
    )
    styles['number'] = ParagraphStyle(
        'Number', parent=styles['body'], leftIndent=13, firstLineIndent=-9,
        spaceAfter=3.2,
    )
    styles['code'] = ParagraphStyle(
        'Code', parent=base['Code'], fontName=FONT_MONO, fontSize=7.4,
        leading=9.7, leftIndent=5, rightIndent=5, borderColor=LINE,
        borderWidth=0.5, borderPadding=6, backColor=colors.HexColor('#F8FAFC'),
        textColor=colors.HexColor('#213040'), spaceBefore=4, spaceAfter=7,
    )
    styles['table'] = ParagraphStyle(
        'TableText', parent=base['BodyText'], fontName=FONT, fontSize=7.25,
        leading=9.4, textColor=INK,
    )
    styles['table_head'] = ParagraphStyle(
        'TableHead', parent=base['BodyText'], fontName=FONT_BOLD, fontSize=7.3,
        leading=9.4, textColor=WHITE,
    )
    styles['callout'] = ParagraphStyle(
        'Callout', parent=styles['body'], fontSize=8.25, leading=11.8,
        spaceAfter=0,
    )
    styles['toc'] = ParagraphStyle(
        'TOC', parent=styles['body'], fontSize=8.3, leading=11.5,
    )
    return styles


STYLES = get_styles()


class ManualDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kwargs):
        super().__init__(filename, **kwargs)
        self._heading_seq = 0

    def beforeDocument(self):
        self._heading_seq = 0
        return super().beforeDocument()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            if style in ('Heading1', 'Heading2'):
                level = 0 if style == 'Heading1' else 1
                text = flowable.getPlainText()
                self._heading_seq += 1
                key = f'h-{self._heading_seq}'
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=level, closed=False)
                self.notify('TOCEntry', (level, text, self.page, key))


def cover_page(canvas, doc):
    # No recurring header/footer; only a subtle page marker.
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 9*mm, w, 9*mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, w, 6*mm, fill=1, stroke=0)
    canvas.restoreState()


def body_page(canvas, doc):
    canvas.saveState()
    w, h = A4
    # top rule and header
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 8.5*mm, w, 8.5*mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont(FONT_BOLD, 7.2)
    canvas.drawString(17*mm, h - 5.6*mm, 'CLEANROOMX | ENGINEERING USER & OPERATIONS MANUAL')
    canvas.setFont(FONT, 7.0)
    canvas.drawRightString(w - 17*mm, h - 5.6*mm, f'{DOC_ID} | {REVISION}')
    # footer
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.45)
    canvas.line(17*mm, 14*mm, w - 17*mm, 14*mm)
    canvas.setFont(FONT, 6.7)
    canvas.setFillColor(MUTED)
    canvas.drawString(17*mm, 9.5*mm, 'Reference copy - verify baseline before use')
    canvas.drawCentredString(w/2, 9.5*mm, 'v0.102.1 | main 9a7ab222')
    canvas.drawRightString(w - 17*mm, 9.5*mm, f'Page {doc.page}')
    canvas.restoreState()


def section_title(text: str):
    p = Paragraph(inline_md(text), STYLES['h1'])
    line = Table([['']], colWidths=[A4[0]-34*mm], rowHeights=[1.2*mm])
    line.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),TEAL),('BOX',(0,0),(-1,-1),0,TEAL)]))
    return KeepTogether([p, line, Spacer(1, 5)])


def part_title(text: str):
    t = Table([[Paragraph(inline_md(text), STYLES['part'])]], colWidths=[A4[0]-34*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),NAVY),
        ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),18),('BOTTOMPADDING',(0,0),(-1,-1),18),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    return KeepTogether([Spacer(1, 28), t, Spacer(1, 18)])


def callout(kind: str, text: str, width: float):
    kind = kind.upper()
    palette = {
        'CONTROL': (TEAL, PALE_TEAL, 'CONTROL'),
        'WARNING': (AMBER, PALE_AMBER, 'WARNING'),
        'STOP': (RED, PALE_RED, 'STOP'),
        'MAIN': (BLUE, PALE_BLUE, 'DEVELOPMENT SNAPSHOT'),
        'NOTE': (MUTED, PALE, 'NOTE'),
        'TIP': (GREEN, colors.HexColor('#ECF7F1'), 'GOOD PRACTICE'),
    }
    accent, bg, label = palette.get(kind, (MUTED, PALE, kind))
    content = Paragraph(f'<b>{label}</b>  {inline_md(text)}', STYLES['callout'])
    tbl = Table([['', content]], colWidths=[3.2*mm, width-3.2*mm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0),accent),('BACKGROUND',(1,0),(1,0),bg),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(0,0),0),('RIGHTPADDING',(0,0),(0,0),0),
        ('TOPPADDING',(0,0),(0,0),0),('BOTTOMPADDING',(0,0),(0,0),0),
        ('LEFTPADDING',(1,0),(1,0),7),('RIGHTPADDING',(1,0),(1,0),7),
        ('TOPPADDING',(1,0),(1,0),6),('BOTTOMPADDING',(1,0),(1,0),6),
        ('BOX',(0,0),(-1,-1),0.45,LINE),
    ]))
    return tbl


def parse_table(lines, width):
    rows = []
    for line in lines:
        rows.append([cell.strip() for cell in line.strip().strip('|').split('|')])
    if len(rows) > 1 and all(re.fullmatch(r':?-{3,}:?', cell.replace(' ', '')) for cell in rows[1]):
        rows.pop(1)
    cols = max(len(r) for r in rows)
    rows = [r + ['']*(cols-len(r)) for r in rows]
    # weighted widths, constrained for readability
    lengths = []
    for c in range(cols):
        lengths.append(max(8, max(len(re.sub(r'[*`]', '', r[c])) for r in rows)))
    total = sum(lengths)
    widths = [width * (x/total) for x in lengths]
    min_w = 23*mm if cols <= 3 else 17*mm
    widths = [max(min_w, x) for x in widths]
    scale = width / sum(widths)
    widths = [x*scale for x in widths]

    data=[]
    for i,row in enumerate(rows):
        st = STYLES['table_head'] if i==0 else STYLES['table']
        data.append([Paragraph(inline_md(cell), st) for cell in row])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY_2),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[WHITE, PALE]),
        ('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),4.5),('RIGHTPADDING',(0,0),(-1,-1),4.5),
        ('TOPPADDING',(0,0),(-1,-1),4.2),('BOTTOMPADDING',(0,0),(-1,-1),4.2),
    ]))
    return t


def cover_story(title_lines):
    brand = title_lines[0] if title_lines else 'CLEANROOMX'
    title = title_lines[1] if len(title_lines) > 1 else 'Engineering User & Operations Manual'
    subtitle = title_lines[2] if len(title_lines) > 2 else 'Design | Simulation | Verification | Evidence'
    # Dark hero panel
    hero = Table([
        [Paragraph(inline_md(brand), STYLES['cover_brand'])],
        [Paragraph(inline_md(title), STYLES['cover_title'])],
        [Paragraph(inline_md(subtitle), STYLES['cover_sub'])],
    ], colWidths=[A4[0]-34*mm])
    hero.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),NAVY),
        ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
        ('TOPPADDING',(0,0),(0,0),24),('BOTTOMPADDING',(0,-1),(0,-1),24),
    ]))
    meta_rows = [
        ['Document ID', DOC_ID],
        ['Revision / issue date', f'{REVISION} | {ISSUE_DATE}'],
        ['Primary software baseline', 'CleanroomX v0.102.1 | Python 3.11 / 3.12 / 3.13'],
        ['Documentation snapshot', 'main @ 9a7ab222878324d03e44c93caea92c927e302ae7'],
        ['Document status', 'Engineering reference manual'],
        ['Repository', '3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform'],
    ]
    meta = Table([[Paragraph(inline_md(a), STYLES['cover_meta']), Paragraph(inline_md(b), STYLES['cover_meta'])] for a,b in meta_rows], colWidths=[45*mm, 132*mm])
    meta.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,-1),PALE),('GRID',(0,0),(-1,-1),0.35,LINE),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('FONTNAME',(0,0),(0,-1),FONT_BOLD),('TEXTCOLOR',(0,0),(0,-1),NAVY_2),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    boundary = callout('WARNING',
        'CleanroomX provides engineering screening, simulation, verification, and software/provenance evidence. '
        'It does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, '
        'manufacturer approval, or regulatory acceptance.', A4[0]-34*mm)
    return [Spacer(1, 18), hero, Spacer(1, 16), meta, Spacer(1, 12), boundary,
            Spacer(1, 12), Paragraph('Built for designers, HVAC engineers, reviewers, QA teams, BIM coordinators, and technical leads.', STYLES['cover_meta']),
            Spacer(1, 4), Paragraph('Use only with the software baseline and project inputs identified in the applicable engineering record.', STYLES['cover_meta'])]


def build(source: Path, output: Path):
    page_w, page_h = A4
    left = right = 17*mm
    top = 17*mm
    bottom = 18*mm
    frame = Frame(left, bottom, page_w-left-right, page_h-top-bottom, id='body')
    doc = ManualDocTemplate(
        str(output), pagesize=A4, leftMargin=left, rightMargin=right,
        topMargin=top, bottomMargin=bottom,
        title='CleanroomX Engineering User & Operations Manual',
        author='CleanroomX contributors',
        subject='Industry-oriented CleanroomX engineering operations manual',
    )
    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[frame], onPage=cover_page),
        PageTemplate(id='body', frames=[frame], onPage=body_page),
    ])

    lines = source.read_text(encoding='utf-8').splitlines()
    story=[]
    idx=0
    cover_lines=[]
    while idx < len(lines) and lines[idx].strip() != '[[COVER_END]]':
        if lines[idx].strip() and not lines[idx].lstrip().startswith('<!--'):
            cover_lines.append(lines[idx].strip())
        idx += 1
    if idx < len(lines) and lines[idx].strip() == '[[COVER_END]]':
        idx += 1
    story.extend(cover_story(cover_lines[:3]))
    story.append(NextPageTemplate('body'))
    story.append(PageBreak())

    usable = page_w-left-right
    paragraph_lines=[]

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            value=' '.join(x.strip() for x in paragraph_lines).strip()
            if value:
                story.append(Paragraph(inline_md(value), STYLES['body']))
            paragraph_lines=[]

    while idx < len(lines):
        line=lines[idx].rstrip()
        stripped=line.strip()
        if not stripped:
            flush_paragraph(); idx+=1; continue
        if stripped.startswith('<!--'):
            flush_paragraph()
            while idx < len(lines) and '-->' not in lines[idx]: idx += 1
            idx += 1; continue
        if stripped == '[[TOC]]':
            flush_paragraph()
            if story and not isinstance(story[-1], PageBreak):
                story.append(PageBreak())
            story.append(Paragraph('Contents', STYLES['h1']))
            toc=TableOfContents()
            toc.levelStyles=[
                ParagraphStyle(name='TOC1', fontName=FONT, fontSize=8.3, leading=11.5, leftIndent=0, firstLineIndent=0, textColor=INK),
                ParagraphStyle(name='TOC2', fontName=FONT, fontSize=7.8, leading=10.5, leftIndent=11, firstLineIndent=0, textColor=MUTED),
            ]
            toc.dotsMinLevel=0
            story.append(toc)
            story.append(PageBreak())
            idx+=1; continue
        if stripped == '[[PAGEBREAK]]':
            flush_paragraph(); story.append(PageBreak()); idx+=1; continue
        if stripped.startswith('```'):
            flush_paragraph(); idx+=1; code=[]
            while idx < len(lines) and not lines[idx].strip().startswith('```'):
                code.append(lines[idx]); idx += 1
            story.append(Preformatted('\n'.join(code), STYLES['code']))
            idx += 1; continue
        if stripped.startswith('|'):
            flush_paragraph(); table_lines=[]
            while idx < len(lines) and lines[idx].strip().startswith('|'):
                table_lines.append(lines[idx].strip()); idx += 1
            story.append(parse_table(table_lines, usable)); story.append(Spacer(1,5)); continue
        mcall=re.match(r'^>\s*\[!(\w+)\]\s*(.*)$', stripped)
        if mcall:
            flush_paragraph(); story.append(callout(mcall.group(1), mcall.group(2), usable)); story.append(Spacer(1,6)); idx+=1; continue
        if stripped.startswith('# '):
            flush_paragraph(); title=stripped[2:].strip()
            if story and not isinstance(story[-1], PageBreak): story.append(PageBreak())
            if title.upper().startswith('PART '):
                story.append(part_title(title))
            else:
                story.append(Paragraph(inline_md(title), STYLES['h1']))
                line_tbl = Table([['']], colWidths=[usable], rowHeights=[1.2*mm])
                line_tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),TEAL),('BOX',(0,0),(-1,-1),0,TEAL)]))
                story.append(line_tbl)
                story.append(Spacer(1, 5))
            idx+=1; continue
        if stripped.startswith('## '):
            flush_paragraph(); story.append(Paragraph(inline_md(stripped[3:].strip()), STYLES['h2'])); idx+=1; continue
        if stripped.startswith('### '):
            flush_paragraph(); story.append(Paragraph(inline_md(stripped[4:].strip()), STYLES['h3'])); idx+=1; continue
        if re.match(r'^[-*]\s+', stripped):
            flush_paragraph(); text=re.sub(r'^[-*]\s+','',stripped); story.append(Paragraph('• '+inline_md(text), STYLES['bullet'])); idx+=1; continue
        mnum=re.match(r'^(\d+)\.\s+(.*)$', stripped)
        if mnum:
            flush_paragraph(); story.append(Paragraph(f'{mnum.group(1)}. '+inline_md(mnum.group(2)), STYLES['number'])); idx+=1; continue
        paragraph_lines.append(line); idx+=1
    flush_paragraph()
    doc.multiBuild(story)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: render_solution_manual_pdf_v2.py SOURCE.md OUTPUT.pdf')
    build(Path(sys.argv[1]), Path(sys.argv[2]))
