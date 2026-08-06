"""
ui/decision_share.py
Executive brief formatting, share exports (copy / email / Teams / PDF / PPT), and pin storage.
Uses mailto + downloads — no OAuth required (enterprise Graph/Teams API can be added later).
"""
from __future__ import annotations

import html
import io
import json
import urllib.parse
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _MPL_OK = True
except ImportError:
    _MPL_OK = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as pdf_canvas
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    _PPT_OK = True
except ImportError:
    _PPT_OK = False


def _now_label() -> str:
    return datetime.now().strftime("%d %b %Y, %H:%M")


def _evidence_line(evidence: dict | None) -> str:
    ev = evidence or {}
    parts = []
    path = ev.get("execution_path")
    if path:
        parts.append(f"Path: {path}")
    if ev.get("resolution_source"):
        parts.append(f"Source: {ev['resolution_source']}")
    trust = ev.get("trust_score")
    if trust is not None:
        parts.append(f"Trust: {trust}/100")
    return " · ".join(parts) if parts else "AI Data Platform — governed semantic analytics"


def build_share_payload(
    *,
    question: str = "",
    narration: dict | None = None,
    result_df: pd.DataFrame | None = None,
    evidence: dict | None = None,
    elapsed: float | None = None,
    sql: str | None = None,
) -> dict[str, Any]:
    """Normalize query/chat bundle into a shareable decision payload."""
    narr = narration or {}
    headline = str(narr.get("headline") or "Decision brief")
    raw = str(narr.get("narrative_text") or narr.get("summary") or "")
    paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
    if not paras and raw.strip():
        paras = [raw.strip()]
    findings = [str(f).strip() for f in (narr.get("key_findings") or []) if str(f).strip()]
    rec = str(narr.get("recommendation") or "").strip()

    row_count = len(result_df) if isinstance(result_df, pd.DataFrame) else 0
    col_count = result_df.shape[1] if isinstance(result_df, pd.DataFrame) else 0

    return {
        "question": (question or "").strip(),
        "headline": headline,
        "paragraphs": paras,
        "findings": findings,
        "recommendation": rec,
        "result_df": result_df,
        "evidence": evidence or {},
        "elapsed": elapsed,
        "sql": (sql or "").strip(),
        "generated_at": _now_label(),
        "row_count": row_count,
        "col_count": col_count,
    }


def format_executive_brief(payload: dict[str, Any], *, teams: bool = False) -> str:
    """Plain-text executive brief for copy, email, or Teams paste."""
    q = payload.get("question") or "Analytics insight"
    lines = [
        "═" * 52,
        "DECISION BRIEF — AI Data Platform",
        f"Generated: {payload.get('generated_at', _now_label())}",
        "═" * 52,
        "",
        f"Question: {q}",
        "",
        f"▶ {payload.get('headline', 'Insight')}",
        "",
    ]
    for p in payload.get("paragraphs") or []:
        lines.append(p)
        lines.append("")
    for i, f in enumerate(payload.get("findings") or [], 1):
        lines.append(f"  {i}. {f}")
    if payload.get("findings"):
        lines.append("")
    if payload.get("recommendation"):
        lines.append(f"Recommendation: {payload['recommendation']}")
        lines.append("")
    rc = payload.get("row_count", 0)
    if rc:
        lines.append(f"Data: {rc:,} rows × {payload.get('col_count', 0)} columns")
    if payload.get("elapsed") is not None:
        lines.append(f"Query time: {payload['elapsed']}s")
    lines.append(_evidence_line(payload.get("evidence")))
    lines.append("")
    lines.append("— Shared from Decision Room · Capgemini AI Data Platform")
    if teams:
        lines.insert(0, "**Decision Brief** (paste into Microsoft Teams)")
    return "\n".join(lines).strip()


def format_teams_message(payload: dict[str, Any]) -> str:
    """Markdown-friendly block for Teams chat paste."""
    brief = format_executive_brief(payload)
    return (
        "**📊 Decision Brief**\n\n"
        f"**{payload.get('headline', 'Insight')}**\n\n"
        + "\n".join(f"• {p}" for p in (payload.get("paragraphs") or [])[:4])
        + "\n\n"
        + (f"**Recommendation:** {payload['recommendation']}\n\n" if payload.get("recommendation") else "")
        + f"_Question: {payload.get('question', '')}_\n"
        + f"_{_evidence_line(payload.get('evidence'))}_"
    )


def _chart_png_bytes(result_df: pd.DataFrame | None, question: str = "") -> bytes | None:
    if not _MPL_OK or result_df is None or result_df.empty:
        return None
    try:
        nums = result_df.select_dtypes(include="number").columns.tolist()
        strs = result_df.select_dtypes(exclude="number").columns.tolist()
        if not nums:
            return None
        x_col = strs[0] if strs else result_df.columns[0]
        y_col = nums[0]
        plot_df = result_df.head(12).copy()
        fig, ax = plt.subplots(figsize=(7, 3.2))
        ax.bar(plot_df[x_col].astype(str), plot_df[y_col].astype(float), color="#6366f1")
        ax.set_title(str(question or "Chart")[:60], fontsize=10)
        ax.tick_params(axis="x", rotation=35, labelsize=7)
        ax.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def payload_headline(_df) -> str:
    return "Chart"


def build_html_brief(payload: dict[str, Any]) -> str:
    """Print-friendly HTML brief (PDF fallback)."""
    paras = "".join(
        f"<p>{html.escape(p)}</p>" for p in (payload.get("paragraphs") or [])
    )
    findings = "".join(
        f"<li>{html.escape(f)}</li>" for f in (payload.get("findings") or [])
    )
    rec = html.escape(payload.get("recommendation") or "")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Decision Brief</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:720px;margin:40px auto;padding:0 24px;color:#1e293b}}
h1{{font-size:22px;color:#4338ca}} .meta{{color:#64748b;font-size:13px}}
.rec{{background:#f1f5f9;padding:12px;border-radius:8px;margin-top:16px}}
footer{{margin-top:32px;font-size:12px;color:#94a3b8;border-top:1px solid #e2e8f0;padding-top:12px}}
</style></head><body>
<h1>{html.escape(payload.get('headline', 'Decision Brief'))}</h1>
<p class="meta">Question: {html.escape(payload.get('question') or '')} · {html.escape(payload.get('generated_at', ''))}</p>
{paras}
{"<ul>" + findings + "</ul>" if findings else ""}
{"<div class='rec'><strong>Recommendation:</strong> " + rec + "</div>" if rec else ""}
<footer>AI Data Platform · Decision Room · {_evidence_line(payload.get('evidence'))}</footer>
</body></html>"""


def build_pdf_bytes(payload: dict[str, Any]) -> bytes | None:
    if not _PDF_OK:
        return None
    try:
        buf = io.BytesIO()
        c = pdf_canvas.Canvas(buf, pagesize=A4)
        w, h = A4
        y = h - 2 * cm
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2 * cm, y, (payload.get("headline") or "Decision Brief")[:70])
        y -= 0.8 * cm
        c.setFont("Helvetica", 9)
        c.drawString(2 * cm, y, f"Question: {(payload.get('question') or '')[:90]}")
        y -= 0.5 * cm
        c.drawString(2 * cm, y, f"Generated: {payload.get('generated_at', '')}")
        y -= 0.8 * cm
        c.setFont("Helvetica", 10)
        for para in (payload.get("paragraphs") or [])[:6]:
            for line in _wrap_text(para, 90):
                if y < 3 * cm:
                    c.showPage()
                    y = h - 2 * cm
                    c.setFont("Helvetica", 10)
                c.drawString(2 * cm, y, line)
                y -= 0.45 * cm
            y -= 0.25 * cm
        if payload.get("recommendation"):
            y -= 0.3 * cm
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2 * cm, y, "Recommendation:")
            y -= 0.45 * cm
            c.setFont("Helvetica", 10)
            for line in _wrap_text(payload["recommendation"], 90):
                c.drawString(2 * cm, y, line)
                y -= 0.45 * cm
        png = _chart_png_bytes(payload.get("result_df"), payload.get("question", ""))
        if png and y > 6 * cm:
            from reportlab.lib.utils import ImageReader
            c.drawImage(ImageReader(io.BytesIO(png)), 2 * cm, 2 * cm, width=14 * cm, height=6 * cm, preserveAspectRatio=True)
        c.setFont("Helvetica", 8)
        c.drawString(2 * cm, 1.2 * cm, _evidence_line(payload.get("evidence"))[:100])
        c.save()
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def _wrap_text(text: str, width: int) -> list[str]:
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def build_pptx_bytes(payload: dict[str, Any]) -> bytes | None:
    if not _PPT_OK:
        return None
    try:
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.35), Inches(9), Inches(1))
        tf = title_box.text_frame
        tf.text = payload.get("headline") or "Decision Brief"
        tf.paragraphs[0].font.size = Pt(24)
        tf.paragraphs[0].font.bold = True

        sub = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(9), Inches(0.5))
        sub.text_frame.text = f"{payload.get('question', '')} · {payload.get('generated_at', '')}"
        sub.text_frame.paragraphs[0].font.size = Pt(11)

        body = slide.shapes.add_textbox(Inches(0.5), Inches(1.85), Inches(5.2), Inches(4.5))
        btf = body.text_frame
        btf.word_wrap = True
        first = True
        for para in (payload.get("paragraphs") or [])[:4]:
            p = btf.paragraphs[0] if first else btf.add_paragraph()
            first = False
            p.text = para
            p.font.size = Pt(13)
            p.level = 0
        if payload.get("recommendation"):
            p = btf.add_paragraph()
            p.text = f"Recommendation: {payload['recommendation']}"
            p.font.size = Pt(12)
            p.font.bold = True

        png = _chart_png_bytes(payload.get("result_df"), payload.get("question", ""))
        if png:
            slide.shapes.add_picture(io.BytesIO(png), Inches(5.9), Inches(1.85), width=Inches(3.8))

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


def pin_decision(payload: dict[str, Any]) -> None:
    pins = list(st.session_state.get("pinned_decisions") or [])
    pin_id = f"pin_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(pins)}"
    sample = None
    rdf = payload.get("result_df")
    if isinstance(rdf, pd.DataFrame) and not rdf.empty:
        sample = rdf.head(5).to_csv(index=False)
    entry = {
        "id": pin_id,
        "question": payload.get("question", ""),
        "headline": payload.get("headline", ""),
        "summary": " ".join((payload.get("paragraphs") or [""])[0].split()[:40]),
        "recommendation": payload.get("recommendation", ""),
        "pinned_at": _now_label(),
        "row_count": payload.get("row_count", 0),
        "sample_csv": sample,
        "suggested_question": payload.get("question", ""),
    }
    pins.insert(0, entry)
    st.session_state["pinned_decisions"] = pins[:8]


def unpin_decision(pin_id: str) -> None:
    pins = [p for p in (st.session_state.get("pinned_decisions") or []) if p.get("id") != pin_id]
    st.session_state["pinned_decisions"] = pins


def render_pinned_strip(on_ask) -> None:
    """Pinned decisions row — shown above Decision Room thread."""
    pins = st.session_state.get("pinned_decisions") or []
    if not pins:
        return
    st.markdown('<div class="dr-pinned-label">📌 Pinned decisions</div>', unsafe_allow_html=True)
    cols = st.columns(min(len(pins), 4))
    for i, pin in enumerate(pins[:4]):
        with cols[i]:
            st.markdown(
                f'<div class="dr-pin-card"><div class="dr-pin-headline">'
                f'{html.escape(str(pin.get("headline", "Insight"))[:48])}</div>'
                f'<div class="dr-pin-meta">{html.escape(str(pin.get("pinned_at", "")))}'
                f' · {pin.get("row_count", 0):,} rows</div></div>',
                unsafe_allow_html=True,
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Open", key=f"pin_open_{pin['id']}", use_container_width=True):
                    q = pin.get("suggested_question") or pin.get("question")
                    if q and callable(on_ask):
                        on_ask(q)
                        st.rerun()
            with c2:
                if st.button("✕", key=f"pin_rm_{pin['id']}", use_container_width=True):
                    unpin_decision(pin["id"])
                    st.rerun()


def render_proactive_landing(working_df: pd.DataFrame, insights: list[dict], on_ask) -> None:
    """Brief-style empty state for Decision Room."""
    st.markdown(
        """
        <div class="dr-landing">
          <div class="dr-landing-eyebrow">🏛️ DECISION ROOM</div>
          <div class="dr-landing-title">Today's data priorities</div>
          <div class="dr-landing-sub">Insights surfaced from your dataset — ask, refine, pin, or share decisions.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not insights:
        st.info("Load data and run a query — proactive priorities will appear here.")
        return
    st.markdown('<div class="dr-priority-grid">', unsafe_allow_html=True)
    cols = st.columns(min(len(insights), 3))
    for i, ins in enumerate(insights[:3]):
        with cols[i]:
            direction = ins.get("direction", "neutral")
            icon = {"up": "🟢", "down": "🔴", "neutral": "🟡"}.get(direction, "🔵")
            st.markdown(
                f'<div class="dr-priority-card">'
                f'<div class="dr-priority-icon">{icon}</div>'
                f'<div class="dr-priority-title">{html.escape(str(ins.get("title", "")))}</div>'
                f'<div class="dr-priority-summary">{html.escape(str(ins.get("summary", "")))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            sq = ins.get("suggested_question")
            if sq and st.button("Explore →", key=f"dr_proactive_{i}", use_container_width=True):
                if callable(on_ask):
                    on_ask(sq)
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _clipboard_js(text: str) -> str:
    escaped = json.dumps(text)
    return f"""
    <script>
    navigator.clipboard.writeText({escaped}).then(function() {{
        window.parent.document.body.dispatchEvent(new CustomEvent('decision-copied'));
    }});
    </script>
    """


def render_share_and_pin(
    payload: dict[str, Any],
    key_prefix: str,
    *,
    show_pin: bool = True,
) -> None:
    """Unified Share popover + Pin button for query/chat results."""
    if not payload.get("headline") and not payload.get("question"):
        return

    col_pin, col_share = st.columns([1, 1.2])
    with col_pin:
        if show_pin and st.button("📌 Pin", key=f"{key_prefix}_pin", use_container_width=True):
            pin_decision(payload)
            st.toast("Pinned to Decision Room", icon="📌")
            st.rerun()

    with col_share:
        with st.popover("📤 Share", use_container_width=True):
            st.caption("Share this decision brief to email, Teams, or slides.")
            brief = format_executive_brief(payload)
            teams_msg = format_teams_message(payload)

            if st.button("📋 Copy brief", key=f"{key_prefix}_copy", use_container_width=True):
                st.session_state[f"{key_prefix}_copy_text"] = brief
                st.toast("Brief ready — copy from box below", icon="📋")

            copy_text = st.session_state.get(f"{key_prefix}_copy_text")
            if copy_text:
                st.text_area("Copy to clipboard", value=copy_text, height=120, key=f"{key_prefix}_ta")

            subject = urllib.parse.quote(f"Decision Brief: {(payload.get('headline') or 'Insight')[:60]}")
            body = urllib.parse.quote(brief[:3500])
            st.markdown(
                f'<a href="mailto:?subject={subject}&body={body}" target="_blank" '
                f'class="dr-share-link">📧 Open in Outlook / Email</a>',
                unsafe_allow_html=True,
            )

            if st.button("💬 Copy for Teams", key=f"{key_prefix}_teams", use_container_width=True):
                st.session_state[f"{key_prefix}_teams_text"] = teams_msg
                st.toast("Teams message ready — copy below", icon="💬")

            teams_text = st.session_state.get(f"{key_prefix}_teams_text")
            if teams_text:
                st.text_area("Paste into Teams", value=teams_text, height=100, key=f"{key_prefix}_teams_ta")

            pdf_bytes = build_pdf_bytes(payload)
            if pdf_bytes:
                st.download_button(
                    "📄 Download PDF",
                    data=pdf_bytes,
                    file_name="decision_brief.pdf",
                    mime="application/pdf",
                    key=f"{key_prefix}_pdf",
                    use_container_width=True,
                )
            else:
                st.download_button(
                    "📄 Download HTML brief",
                    data=build_html_brief(payload).encode("utf-8"),
                    file_name="decision_brief.html",
                    mime="text/html",
                    key=f"{key_prefix}_html",
                    use_container_width=True,
                )

            ppt_bytes = build_pptx_bytes(payload)
            if ppt_bytes:
                st.download_button(
                    "📊 Download PowerPoint",
                    data=ppt_bytes,
                    file_name="decision_brief.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    key=f"{key_prefix}_ppt",
                    use_container_width=True,
                )
            else:
                st.caption("Install python-pptx for PowerPoint export.")

            rdf = payload.get("result_df")
            if isinstance(rdf, pd.DataFrame) and not rdf.empty:
                st.download_button(
                    "⬇️ Download data (CSV)",
                    data=rdf.to_csv(index=False).encode(),
                    file_name="decision_data.csv",
                    mime="text/csv",
                    key=f"{key_prefix}_csv",
                    use_container_width=True,
                )
