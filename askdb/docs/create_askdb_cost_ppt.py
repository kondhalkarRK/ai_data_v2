#!/usr/bin/env python3
"""Generate AskDB_AI_Cost_Comparison.pptx (4 slides, 16:9, navy theme) with python-pptx.
Run:  pip install python-pptx   then   python create_askdb_cost_ppt.py
All figures are illustrative estimates in USD, not live vendor quotes."""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION

# ---------- design tokens ----------
NAVY, CARD_A, CARD_B = RGBColor(0x07,0x1A,0x33), RGBColor(0x11,0x31,0x5C), RGBColor(0x0B,0x24,0x46)
BLUE, CYAN, WHITE, MUTED = RGBColor(0x3B,0x82,0xF6), RGBColor(0x22,0xD3,0xEE), RGBColor(0xFF,0xFF,0xFF), RGBColor(0xA9,0xBC,0xD6)
FONT, M, W, H = "Segoe UI", 0.7, 13.333, 7.5          # font, side margin, slide size (inches)
FOOTER = "AskDB | AI Cost Estimates | October 2026"

# ---------- reusable helpers ----------
def new_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])      # blank layout
    s.background.fill.solid(); s.background.fill.fore_color.rgb = NAVY   # navy on every slide
    return s

def text(s, x, y, w, h, t, size=18, color=WHITE, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, name=None):
    """Native, editable text box. `t` may contain newlines (one paragraph each)."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name: tb.name = name
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(t.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; r = p.add_run(); r.text = line
        r.font.size, r.font.bold, r.font.name, r.font.color.rgb = Pt(size), bold, FONT, color
    return tb

def rect(s, x, y, w, h, line=None, rounded=True, gradient=True, name=None):
    """Card shape with subtle navy gradient and optional accent outline."""
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                            Inches(x), Inches(y), Inches(w), Inches(h))
    if name: sh.name = name
    if rounded: sh.adjustments[0] = 0.07
    if gradient:
        sh.fill.gradient(); sh.fill.gradient_angle = 90
        sh.fill.gradient_stops[0].color.rgb, sh.fill.gradient_stops[1].color.rgb = CARD_A, CARD_B
    else:
        sh.fill.solid(); sh.fill.fore_color.rgb = CARD_B
    if line: sh.line.color.rgb, sh.line.width = line, Pt(2.25)
    else:    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh

def heading(s, title, kicker=None):
    """Accent bar + optional kicker + large title, same position on every content slide."""
    rect(s, M, 0.62, 0.9, 0.07, rounded=False, gradient=False).fill.fore_color.rgb = CYAN
    if kicker: text(s, M, 0.8, 8, 0.3, kicker.upper(), 12, CYAN, True)
    text(s, M, 1.1, W - 2*M, 0.8, title, 34, WHITE, True)

def kpi_card(s, x, y, w, h, value, label, accent=BLUE, val_size=44, highlight=False):
    """KPI card: big value, muted label, thin accent strip on the left."""
    rect(s, x, y, w, h, line=CYAN if highlight else None, name="KPI " + label)
    rect(s, x + 0.25, y + 0.3, 0.07, h - 0.6, rounded=False, gradient=False).fill.fore_color.rgb = accent
    text(s, x + 0.55, y + 0.25, w - 0.8, h * 0.5, value, val_size, WHITE, True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.55, y + h * 0.62, w - 0.8, h * 0.3, label, 16, MUTED)

def footer(s, n):
    text(s, M, H - 0.5, 8, 0.25, FOOTER, 10, MUTED)
    text(s, W - M - 1, H - 0.5, 1, 0.25, str(n), 10, MUTED, align=PP_ALIGN.RIGHT)

def bar_chart(s, x, y, w, h, cats, vals, colors, title):
    """Native horizontal bar chart; one colour per bar (Hybrid = cyan)."""
    cd = CategoryChartData(); cd.categories = cats; cd.add_series("Monthly AI cost (USD)", vals)
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    gf.name = "Monthly cost chart"; ch = gf.chart
    ch.has_legend = False; ch.has_title = True
    ch.chart_title.text_frame.text = title
    f = ch.chart_title.text_frame.paragraphs[0].runs[0].font; f.size, f.bold, f.name, f.color.rgb = Pt(14), True, FONT, MUTED
    ca, va = ch.category_axis, ch.value_axis
    ca.reverse_order = True; ca.format.line.fill.background(); ca.has_major_gridlines = False
    ca.tick_labels.font.size, ca.tick_labels.font.color.rgb, ca.tick_labels.font.name = Pt(14), WHITE, FONT
    va.visible = False; va.has_major_gridlines = False; va.maximum_scale = 1900; va.minimum_scale = 0
    pl = ch.plots[0]; pl.gap_width = 55; pl.has_data_labels = True
    dl = pl.data_labels; dl.number_format, dl.number_format_is_linked = '"$"#,##0', False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size, dl.font.bold, dl.font.name, dl.font.color.rgb = Pt(16), True, FONT, WHITE
    for i, c in enumerate(colors):
        pt = pl.series[0].points[i]; pt.format.fill.solid(); pt.format.fill.fore_color.rgb = c

# ---------- data (USD) ----------
OPTIONS = [("GPT-5 mini (Small)", "$297", "$3,564", 297, BLUE),
           ("GPT-5 High", "$1,485", "$17,820", 1485, BLUE),
           ("Hybrid (80% Small, 20% High)", "$535", "$6,420", 535, CYAN)]

prs = Presentation(); prs.slide_width, prs.slide_height = Inches(W), Inches(H)

# ---- Slide 1: overview ----
s = new_slide(prs)
rect(s, M, 1.1, 0.9, 0.07, rounded=False, gradient=False).fill.fore_color.rgb = CYAN
text(s, M, 1.4, W - 2*M, 1.5, "AskDB \u2014 AI-Powered\nBusiness Intelligence", 48, WHITE, True, name="Title")
text(s, M, 3.05, W - 2*M, 0.5, "AI Model Cost Comparison  |  100 Users", 24, CYAN)
cw, gap = (W - 2*M - 2*0.4) / 3, 0.4
for i, (v, l) in enumerate([("100", "registered users"), ("60", "active users assumed"), ("19,800", "questions / month")]):
    kpi_card(s, M + i * (cw + gap), 4.0, cw, 1.9, v, l, BLUE if i != 2 else CYAN, 54)
text(s, M, 6.2, W - 2*M, 0.35, "Estimated AI API costs, excluding hosting and engineering.", 14, MUTED)
footer(s, 1)

# ---- Slide 2: monthly + annual cost ----
s = new_slide(prs); heading(s, "Monthly and Annual AI Costs", "Model strategy comparison")
bar_chart(s, M, 2.1, 5.6, 3.5, ["GPT-5 mini", "GPT-5 High", "Hybrid 80/20"], [o[3] for o in OPTIONS], [o[4] for o in OPTIONS], "Monthly AI cost (USD)")
cx, cwid, ch_ = 6.7, W - M - 6.7, 1.1
for i, (name, mo, yr, _, col) in enumerate(OPTIONS):
    y = 2.1 + i * (ch_ + 0.2); hl = col == CYAN
    rect(s, cx, y, cwid, ch_, line=CYAN if hl else None, name="Option " + name)
    text(s, cx + 0.3, y + 0.1, 2.3, 0.9, name + ("\nRecommended" if hl else ""), 14, CYAN if hl else WHITE, True, MSO_ANCHOR.MIDDLE)
    text(s, cx + 2.75, y + 0.15, 1.45, 0.5, mo, 24, WHITE, True, PP_ALIGN.RIGHT); text(s, cx + 2.75, y + 0.7, 1.45, 0.3, "per month", 11, MUTED, align=PP_ALIGN.RIGHT)
    text(s, cx + 4.4, y + 0.2, 1.3, 0.45, yr, 18, MUTED if not hl else CYAN, True, PP_ALIGN.RIGHT); text(s, cx + 4.4, y + 0.7, 1.3, 0.3, "per year", 11, MUTED, align=PP_ALIGN.RIGHT)
text(s, M, 5.85, W - 2*M, 0.9,
     "Assumptions: 60 active users \u00d7 ~330 questions = 19,800 questions/month, about $0.015 per question (Small) and $0.075 (High). "
     "Hybrid = 80% Small + 20% High, rounded to $535/month ($6,420/year). Illustrative estimates, not live quotes; "
     "verify current model IDs, availability and pricing before presenting.", 12, MUTED)
footer(s, 2)

# ---- Slide 3: recommended budget ----
s = new_slide(prs); heading(s, "Recommended Budget", "Planning view")
cw = (W - 2*M - 2*0.4) / 3
kpi_card(s, M, 2.3, cw, 2.1, "~$535", "Hybrid AI cost per month", BLUE, 40)
kpi_card(s, M + cw + 0.4, 2.3, cw, 2.1, "~$6,420", "Hybrid AI cost per year", BLUE, 40)
kpi_card(s, M + 2*(cw + 0.4), 2.3, cw, 2.1, "$500\u2013$1,500", "Total app operating budget / month", CYAN, 28, highlight=True)
text(s, M + 2*(cw + 0.4) + 0.55, 4.5, cw - 0.8, 0.5, "Includes basic hosting, database, monitoring and contingency.", 12, MUTED)
rect(s, M, 5.15, W - 2*M, 1.25, name="Budget note")
text(s, M + 0.35, 5.25, W - 2*M - 0.7, 1.05,
     "The total application budget is an independent planning estimate. Reconcile it with the AI costs, the infrastructure plan and actual vendor "
     "quotations. Excludes engineering salaries and enterprise-grade infrastructure.", 14, WHITE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, 3)

# ---- Slide 4: recommendation ----
s = new_slide(prs); heading(s, "The Smart Choice for AskDB", "Recommendation")
recs = ["Use a smaller model for straightforward business questions.",
        "Route complex analysis to a stronger reasoning model.",
        "Track cost per successful answer and enforce per-user usage limits."]
for i, r in enumerate(recs):
    y = 2.2 + i * 1.2
    rect(s, M, y, W - 2*M, 1.0, name=f"Recommendation {i+1}")
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(M + 0.3), Inches(y + 0.2), Inches(0.6), Inches(0.6))
    c.fill.solid(); c.fill.fore_color.rgb = CYAN if i == 1 else BLUE; c.line.fill.background(); c.shadow.inherit = False
    tf = c.text_frame; tf.margin_left = tf.margin_right = 0; p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    run = p.add_run(); run.text = str(i + 1); run.font.size, run.font.bold, run.font.name, run.font.color.rgb = Pt(20), True, FONT, NAVY
    text(s, M + 1.2, y + 0.1, W - 2*M - 1.5, 0.8, r, 20, WHITE, False, anchor=MSO_ANCHOR.MIDDLE)
text(s, M, 5.95, W - 2*M, 0.6, "AskDB \u2014 Intelligence, refined.", 28, CYAN, True, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
footer(s, 4)

prs.save("AskDB_AI_Cost_Comparison.pptx"); print("Saved AskDB_AI_Cost_Comparison.pptx")
