from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
INK = colors.HexColor("#17372f")
GREEN = colors.HexColor("#276a52")
MINT = colors.HexColor("#e9f2ed")
LINE = colors.HexColor("#d9e2dc")
MUTED = colors.HexColor("#66776e")
FONT_DIR = Path("C:/Windows/Fonts")
if (FONT_DIR / "arial.ttf").exists() and (FONT_DIR / "arialbd.ttf").exists():
    pdfmetrics.registerFont(TTFont("Forge", str(FONT_DIR / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("Forge-Bold", str(FONT_DIR / "arialbd.ttf")))
    REGULAR, BOLD = "Forge", "Forge-Bold"
else:
    REGULAR, BOLD = "Helvetica", "Helvetica-Bold"
BASE = getSampleStyleSheet()
STYLE = {
    "title": ParagraphStyle("T", parent=BASE["Title"], fontName=BOLD, fontSize=23, leading=28,
        textColor=INK, alignment=0, spaceAfter=10),
    "h1": ParagraphStyle("H1", parent=BASE["Heading1"], fontName=BOLD, fontSize=14, leading=18,
        textColor=INK, spaceBefore=12, spaceAfter=6, keepWithNext=True),
    "h2": ParagraphStyle("H2", parent=BASE["Heading2"], fontName=BOLD, fontSize=10.5, leading=13,
        textColor=GREEN, spaceBefore=8, spaceAfter=4, keepWithNext=True),
    "h3": ParagraphStyle("H3", parent=BASE["Heading3"], fontName=BOLD, fontSize=9.2, leading=11.5,
        textColor=GREEN, spaceBefore=6, spaceAfter=3, keepWithNext=True),
    "body": ParagraphStyle("B", parent=BASE["BodyText"], fontName=REGULAR, fontSize=8.7,
        leading=12.4, textColor=INK, spaceAfter=5),
    "bullet": ParagraphStyle("L", parent=BASE["BodyText"], fontName=REGULAR, fontSize=8.5,
        leading=12, textColor=INK, leftIndent=12, firstLineIndent=-8, spaceAfter=2),
    "meta": ParagraphStyle("M", parent=BASE["BodyText"], fontName=REGULAR, fontSize=8.2,
        leading=11, textColor=MUTED, spaceAfter=3),
    "th": ParagraphStyle("TH", parent=BASE["BodyText"], fontName=BOLD, fontSize=7.8,
        leading=9.5, textColor=colors.white),
    "td": ParagraphStyle("TD", parent=BASE["BodyText"], fontName=REGULAR, fontSize=7.5,
        leading=9.7, textColor=INK),
}


def inline(value):
    links = []
    def hold_link(match):
        token = f"CODEXLINK{len(links)}TOKEN"
        links.append((token, match.group(1), match.group(2)))
        return token
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", hold_link, value)
    value = escape(value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", value)
    tick = chr(96)
    value = re.sub("(?<!"+tick+")"+tick+"([^"+tick+"]+)"+tick+"(?!"+tick+")",
                   r"<font name='Forge-Bold'>\1</font>", value)
    value = re.sub(r"(https?://[^\s]+)", r"<font color='#276a52'>\1</font>", value)
    for token, label, href in links:
        anchor = f"<link href='{escape(href)}' color='#276a52'>{escape(label)}</link>"
        value = value.replace(token, anchor)
    return value


def build_story(markdown):
    lines = markdown.replace("—", "-").replace("–", "-").replace("‑", "-").splitlines()
    story, index, titled = [], 0, False
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line in ("---", "***", "___"):
            index += 1
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), STYLE["title"] if not titled else STYLE["h1"]))
            titled = True
            index += 1
            continue
        if line.startswith("## "):
            if line.startswith("## 8. Assumptions"):
                story.append(PageBreak())
            story.append(Paragraph(inline(line[3:]), STYLE["h1"]))
            index += 1
            continue
        if line.startswith("#### "):
            story.append(Paragraph(inline(line[5:]), STYLE["h3"]))
            index += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(inline(line[4:]), STYLE["h2"]))
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                index += 1
            if rows:
                width = A4[0] - 36 * mm
                columns = max(map(len, rows))
                first = min(42 * mm, width * .30)
                widths = [first] + [(width-first)/max(columns-1, 1)] * (columns-1)
                data = []
                for rowno, row in enumerate(rows):
                    cell_style = STYLE["th"] if rowno == 0 else STYLE["td"]
                    data.append([Paragraph(inline(c), cell_style) for c in row] +
                                [Paragraph("", cell_style)] * (columns-len(row)))
                table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, MINT]),
                    ("GRID", (0, 0), (-1, -1), .35, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.extend([table, Spacer(1, 3*mm)])
            continue
        if line.startswith("- "):
            story.append(Paragraph("• " + inline(line[2:]), STYLE["bullet"]))
        elif line.startswith("**"):
            story.append(Paragraph(inline(line), STYLE["meta"]))
        else:
            story.append(Paragraph(inline(line), STYLE["body"]))
        index += 1
    return story


def decorate(canvas, doc):
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.rect(0, height-8*mm, width, 8*mm, stroke=0, fill=1)
    canvas.setFont(BOLD, 8)
    canvas.setFillColor(GREEN)
    canvas.drawString(18*mm, 12*mm, "FORGEQUOTE / TECHNICAL DESIGN")
    canvas.setFont(REGULAR, 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width-18*mm, 12*mm, f"REVIEW BUILD · {doc.page}")
    canvas.restoreState()


def main():
    source = (ROOT / "TDD.md").read_text(encoding="utf-8-sig")
    pdf = ROOT / "TDD.pdf"
    doc = BaseDocTemplate(str(pdf), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
        topMargin=19*mm, bottomMargin=19*mm, title="ForgeQuote Technical Design")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main",
        leftPadding=0, rightPadding=0, topPadding=2*mm, bottomPadding=5*mm)
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=decorate)])
    doc.build(build_story(source))
    with zipfile.ZipFile(ROOT / "ForgeQuote_submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(pdf, "TDD.pdf")
        archive.write(ROOT / "deployment.md", "deployment.md")


if __name__ == "__main__":
    main()
