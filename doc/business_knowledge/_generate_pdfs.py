"""Generate PDF copies of India PV business SOPs from Markdown sources."""
from pathlib import Path
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, KeepTogether,
)

ROOT = Path("doc/business_knowledge")


def md_to_flowables(text: str, styles):
    story = []
    lines = text.splitlines()
    buf = []

    def flush_para():
        nonlocal buf
        if not buf:
            return
        raw = " ".join(buf).strip()
        buf = []
        if not raw:
            return
        # bold **x**
        raw = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", raw)
        raw = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", raw)
        story.append(Paragraph(raw, styles["Body"]))
        story.append(Spacer(1, 4))

    for line in lines:
        if line.startswith("# "):
            flush_para()
            story.append(Paragraph(line[2:].strip(), styles["TitleDoc"]))
            story.append(Spacer(1, 8))
        elif line.startswith("## "):
            flush_para()
            story.append(Spacer(1, 8))
            story.append(Paragraph(line[3:].strip(), styles["H2"]))
            story.append(Spacer(1, 4))
        elif line.startswith("### "):
            flush_para()
            story.append(Paragraph(line[4:].strip(), styles["H3"]))
            story.append(Spacer(1, 3))
        elif line.startswith("|") and "---" not in line:
            flush_para()
            cells = [c.strip() for c in line.strip("|").split("|")]
            row = " — ".join(cells)
            row = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", row)
            story.append(Paragraph(row, styles["TableRow"]))
        elif line.startswith("- ") or line.startswith("1. ") or re.match(r"^\d+\.\s", line):
            flush_para()
            item = re.sub(r"^[-*\d.]+\s*", "", line).strip()
            item = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", item)
            story.append(Paragraph(f"• {item}", styles["Body"]))
        elif line.strip() == "---":
            flush_para()
            story.append(Spacer(1, 6))
        elif line.strip() == "":
            flush_para()
        else:
            buf.append(line.strip())
    flush_para()
    return story


def build_styles():
    base = getSampleStyleSheet()
    styles = {
        "TitleDoc": ParagraphStyle(
            "TitleDoc", parent=base["Heading1"], fontSize=14, spaceAfter=6, leading=18
        ),
        "H2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontSize=12, spaceBefore=6, leading=15
        ),
        "H3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontSize=10, spaceBefore=4, leading=13
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontSize=9, leading=12
        ),
        "TableRow": ParagraphStyle(
            "TableRow", parent=base["BodyText"], fontSize=8, leading=10, leftIndent=6
        ),
    }
    return styles


def main():
    styles = build_styles()
    written = []
    for md in sorted(ROOT.glob("*.md")):
        pdf_path = md.with_suffix(".pdf")
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=md.stem,
        )
        text = md.read_text(encoding="utf-8")
        story = md_to_flowables(text, styles)
        doc.build(story)
        written.append(pdf_path.name)
    print("PDF_OK", len(written), written)


if __name__ == "__main__":
    main()
