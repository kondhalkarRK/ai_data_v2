"""
ui/tab_query.py
Ask mode + Chat with Data (Prompt 2 UI).
"""
from __future__ import annotations

import html
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from core.nlq_engine import run_query
from core.chart_engine import auto_chart_type, build_chart

try:
    from core.conversation_state import get_state, clear_state, detect_followup
except Exception:
    def get_state():
        return st.session_state.get("conversation_state") or {}

    def clear_state():
        st.session_state.conversation_state = {}

    def detect_followup(q):
        return False

try:
    from core.question_normaliser import detect_oob
except Exception:
    def detect_oob(q):
        return False

try:
    from core.evidence_builder import get_execution_badge
except Exception:
    def get_execution_badge(evidence):
        return {"icon": "⚠️", "label": "AI Generated", "colour": "orange", "tooltip": ""}

try:
    from config.constants import (
        BADGE_CACHED,
        BADGE_DETERMINISTIC,
        BADGE_FALLBACK,
        BADGE_OOB,
    )
except Exception:
    BADGE_CACHED = {"icon": "🔒", "label": "Cached", "colour": "blue"}
    BADGE_DETERMINISTIC = {"icon": "✅", "label": "Deterministic", "colour": "green"}
    BADGE_FALLBACK = {"icon": "⚠️", "label": "AI Generated", "colour": "orange"}
    BADGE_OOB = {"icon": "🚫", "label": "Out of Scope", "colour": "red"}

# Feature engines — graceful fallback
try:
    from features.proactive_engine import ProactiveEngine
    proactive_engine = ProactiveEngine()
except Exception:
    proactive_engine = None

try:
    from features.whatif_engine import WhatIfEngine
    whatif_engine = WhatIfEngine()
except Exception:
    whatif_engine = None

try:
    from features.anomaly_engine import AnomalyEngine
    anomaly_engine = AnomalyEngine()
except Exception:
    anomaly_engine = None

try:
    from features.narration_engine import NarrationEngine
    narration_engine = NarrationEngine()
except Exception:
    narration_engine = None


def _safe_proactive_insights(df):
    if proactive_engine is None:
        return []
    try:
        return proactive_engine.generate_proactive_insights(df)
    except Exception:
        return []


def _safe_suggested_questions(df, limit=4):
    if proactive_engine is None:
        return [
            "Show revenue by colour",
            "Top 10 salespeople by revenue",
            "Show revenue trend by month",
            "Find anomalies in my data",
        ][:limit]
    try:
        return proactive_engine.get_suggested_questions(df, limit=limit)
    except Exception:
        return []


def _safe_narration(result_df, question, intent, evidence):
    if narration_engine is None:
        return None
    try:
        return narration_engine.generate_narration(
            result_df, question, intent, evidence, mode="standard"
        )
    except Exception:
        return None


def _safe_whatif_detect(question):
    if whatif_engine is None:
        return False
    try:
        return whatif_engine.detect_whatif_query(question)
    except Exception:
        return False


def _safe_anomaly_detect(df):
    if anomaly_engine is None:
        return []
    try:
        return anomaly_engine.detect_anomalies(df)
    except Exception:
        return []


def _similar_question_suggestions(question: str) -> list[str]:
    return _safe_suggested_questions(
        st.session_state.get("_last_working_df"),
        limit=3,
    ) or [
        "Show revenue by colour",
        "Top 10 by revenue",
        "Show monthly trend",
    ]


def _badge_css_class(badge: dict | None, evidence: dict | None = None) -> str:
    path = (evidence or {}).get("execution_path")
    if path == "deterministic":
        return "badge-deterministic"
    if path == "cache":
        return "badge-cached"
    colour = (badge or {}).get("colour", "orange")
    return {
        "green": "badge-deterministic",
        "orange": "badge-fallback",
        "blue": "badge-cached",
        "red": "badge-oob",
    }.get(colour, "badge-fallback")


def _fmt_num(v) -> str:
    try:
        return f"{float(v):,.1f}"
    except Exception:
        return str(v)


# ─────────────────────────────────────────────────────────────
# Shared render helpers
# ─────────────────────────────────────────────────────────────

def render_narration_card(narration: dict | None):
    if not narration:
        return
    headline = html.escape(str(narration.get("headline") or "Insight"))
    body = html.escape(str(narration.get("narrative_text") or narration.get("summary") or ""))
    st.markdown(
        f"""
        <div class="narration-card fade-in-up">
          <div class="narration-headline">📊 {headline}</div>
          <div class="narration-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    findings = narration.get("key_findings") or []
    if findings:
        items = "".join(
            f'<div class="narration-finding-item">• {html.escape(str(f))}</div>'
            for f in findings
        )
        st.markdown(
            f'<div class="narration-findings"><b>Key Findings:</b>{items}</div>',
            unsafe_allow_html=True,
        )
    if narration.get("recommendation"):
        st.markdown(
            f"""
            <div class="narration-recommendation">
              💡 {html.escape(str(narration['recommendation']))}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_whatif_card(whatif_result: dict | None):
    if not whatif_result:
        st.info("No what-if result.")
        return

    narrative = whatif_result.get("narrative") or ""
    render_narration_card({
        "headline": "What-If Analysis",
        "narrative_text": narrative,
        "key_findings": [],
        "recommendation": None,
    })

    base = whatif_result.get("baseline") or {}
    scen = whatif_result.get("scenario") or {}
    delta = whatif_result.get("delta") or {}
    direction = delta.get("direction", "up")
    colour = "#10b981" if direction == "up" else "#ef4444"
    icon = "⬆️" if direction == "up" else "⬇️"
    scen_cls = "whatif-scenario-box-up" if direction == "up" else "whatif-scenario-box-down"

    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        st.markdown(
            f"""
            <div class="whatif-baseline-box">
              <div class="whatif-value-label">BASELINE</div>
              <div class="whatif-value-number" style="color:#a5b4fc;">
                {_fmt_num(base.get('value', 0))}
              </div>
              <div style="font-size:11px;color:#64748b;">
                {html.escape(str(base.get('label', '')))}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        pct = float(delta.get("percent") or 0)
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;padding:16px 0;">
              <div style="font-size:28px;">{icon}</div>
              <div style="font-size:16px;font-weight:700;color:{colour};">
                {pct:+.1f}%
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="{scen_cls}">
              <div class="whatif-value-label">SCENARIO</div>
              <div class="whatif-value-number" style="color:{colour};">
                {_fmt_num(scen.get('value', 0))}
              </div>
              <div style="font-size:11px;color:#64748b;">
                {html.escape(str(scen.get('label', '')))}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    chart = whatif_result.get("chart_data")
    if isinstance(chart, pd.DataFrame) and not chart.empty:
        try:
            build_chart(chart, "Bar", "scenario", "value")
        except Exception:
            pass

    assumptions = whatif_result.get("assumptions") or []
    if assumptions:
        st.markdown("**Assumptions:**")
        for a in assumptions:
            st.markdown(f"• {a}")


def render_anomaly_cards(anomalies: list[dict], working_df=None):
    if not anomalies:
        st.info("No anomalies detected.")
        return

    engine = anomaly_engine
    for i, anomaly in enumerate(anomalies[:5]):
        badge = (
            engine.get_anomaly_badge(anomaly)
            if engine is not None
            else {"icon": "🔵", "colour": "blue", "label": "Info"}
        )
        sev = anomaly.get("severity", "info")
        colours = {
            "critical": ("#ef4444", "#ef4444", "rgba(239,68,68,0.1)", "#fca5a5"),
            "warning": ("#f59e0b", "#f59e0b", "rgba(245,158,11,0.1)", "#fcd34d"),
            "info": ("#3b82f6", "#3b82f6", "rgba(59,130,246,0.1)", "#93c5fd"),
        }
        border, left, bg, fg = colours.get(sev, colours["info"])
        col_name = html.escape(str(anomaly.get("column", "")).replace("_", " ").title())
        desc = html.escape(str(anomaly.get("description", "")))
        st.markdown(
            f"""
            <div style="background:rgba(15,23,42,0.7);border:1px solid {border};
                        border-left:3px solid {left};border-radius:8px;
                        padding:12px 16px;margin:6px 0;display:flex;
                        align-items:flex-start;gap:12px;">
              <div style="font-size:18px;flex-shrink:0;">{badge.get('icon','')}</div>
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                  <span style="font-size:12px;font-weight:700;color:#e2e8f0;">{col_name}</span>
                  <span style="background:{bg};color:{fg};font-size:10px;font-weight:600;
                               padding:1px 7px;border-radius:8px;text-transform:uppercase;">
                    {html.escape(sev)}
                  </span>
                </div>
                <div style="font-size:12px;color:#94a3b8;line-height:1.5;">{desc}</div>
                <div style="font-size:11px;color:#64748b;margin-top:6px;display:flex;gap:16px;">
                  <span>Expected: <strong style="color:#a5b4fc;">{_fmt_num(anomaly.get('expected',0))}</strong></span>
                  <span>Actual: <strong style="color:#f87171;">{_fmt_num(anomaly.get('value',0))}</strong></span>
                  <span>Deviation: <strong style="color:#fbbf24;">{float(anomaly.get('deviation_pct') or 0):+.1f}%</strong></span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        sq = anomaly.get("suggested_question")
        if sq and working_df is not None:
            if st.button(f"🔍 {sq}", key=f"anomaly_drill_{i}"):
                process_chat_message(sq, working_df)


def render_user_bubble(message: dict):
    content = html.escape(str(message.get("content", "")))
    ts = html.escape(str(message.get("timestamp", "")))
    st.markdown(
        f"""
        <div class="user-bubble">
          <div class="user-bubble-text">{content}</div>
          <div class="user-avatar">👤</div>
        </div>
        <div class="msg-timestamp-right">{ts}</div>
        """,
        unsafe_allow_html=True,
    )


def render_assistant_bubble(message, narration_on, view_mode, working_df=None):
    ts = html.escape(str(message.get("timestamp", "")))
    mtype = message.get("message_type", "query")
    data = message.get("data") or {}

    st.markdown(
        """
        <div class="assistant-bubble">
          <div class="assistant-avatar">🤖</div>
          <div class="assistant-card">
        """,
        unsafe_allow_html=True,
    )

    if mtype == "error":
        err = html.escape(str(message.get("content") or data.get("error") or "Error"))
        is_oob = data.get("error_type") == "out_of_scope" or "out of scope" in err.lower()
        cls = "chat-oob-card" if is_oob else "chat-error-card"
        st.markdown(
            f'<div class="{cls}"><strong>{err}</strong></div>',
            unsafe_allow_html=True,
        )
        for i, s in enumerate((data.get("suggestions") or [])[:3]):
            if st.button(s, key=f"chat_err_sug_{ts}_{i}"):
                process_chat_message(s, working_df)

    elif mtype == "anomaly":
        narr = data.get("narration") or {}
        render_narration_card(narr)
        render_anomaly_cards(data.get("anomalies") or [], working_df=working_df)

    elif mtype == "whatif":
        render_whatif_card(data.get("whatif_result"))

    elif mtype == "query":
        evidence = data.get("evidence")
        badge = get_execution_badge(evidence) if evidence else BADGE_FALLBACK
        css = _badge_css_class(badge, evidence)
        rows = 0
        rdf = data.get("result_df")
        if isinstance(rdf, pd.DataFrame):
            rows = len(rdf)
        st.markdown(
            f"""
            <div class="result-header-bar">
              <span class="{css}">{badge.get('icon','')} {html.escape(badge.get('label',''))}</span>
              <span class="result-stat-pill">📋 {rows:,} rows</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        force = False
        if narration_engine is not None:
            try:
                force = narration_engine.should_auto_narrate(
                    str(data.get("source_question") or "")
                )
            except Exception:
                force = False

        show_narration = bool(narration_on) or force
        vm = str(view_mode or "Both")

        if show_narration and vm in ("Narrative", "Both"):
            render_narration_card(data.get("narration"))
        elif force:
            render_narration_card(data.get("narration"))

        show_table = vm in ("Table", "Both") or not show_narration
        if show_table and isinstance(rdf, pd.DataFrame):
            st.dataframe(rdf, use_container_width=True, height=min(320, 40 + len(rdf) * 35))

    st.markdown("</div></div>", unsafe_allow_html=True)
    st.markdown(f'<div class="msg-timestamp">{ts}</div>', unsafe_allow_html=True)


def process_chat_message(question: str, working_df: pd.DataFrame):
    if working_df is None or not question or not str(question).strip():
        return

    q = question.strip()
    now = datetime.now().strftime("%H:%M")
    narration_on = st.session_state.get("chat_narration_on", True)
    view_mode = st.session_state.get("chat_view_mode", "Both")

    st.session_state.setdefault("chat_messages", [])
    st.session_state.chat_messages.append({
        "role": "user",
        "content": q,
        "timestamp": now,
        "message_type": "query",
        "data": {},
        "display_mode": view_mode,
        "narration_active": narration_on,
    })

    is_oob = detect_oob(q)
    is_whatif = _safe_whatif_detect(q)
    anomaly_tokens = [
        "anomaly", "anomalies", "unusual", "outlier",
        "what's wrong", "flag", "anything strange", "stands out",
        "anything odd", "what stands out",
    ]
    is_anomaly = any(tok in q.lower() for tok in anomaly_tokens)

    if is_oob:
        assistant = {
            "role": "assistant",
            "content": "That question is outside what I can answer from this dataset.",
            "message_type": "error",
            "data": {
                "error_type": "out_of_scope",
                "suggestions": _safe_suggested_questions(working_df),
            },
        }
    elif is_whatif and whatif_engine is not None:
        with st.spinner("🔍 Running scenario..."):
            scenario = whatif_engine.parse_scenario(q)
            whatif_result = whatif_engine.run_scenario(working_df, scenario)
            narrative = (
                narration_engine.generate_whatif_narration(whatif_result)
                if narration_engine is not None
                else whatif_result.get("narrative", "")
            )
        assistant = {
            "role": "assistant",
            "content": narrative,
            "message_type": "whatif",
            "data": {
                "whatif_result": whatif_result,
                "narration": {
                    "narrative_text": narrative,
                    "headline": "What-If Analysis",
                    "key_findings": [],
                },
            },
        }
    elif is_anomaly:
        with st.spinner("⚠️ Scanning for anomalies..."):
            anomalies = _safe_anomaly_detect(working_df)
            summary = (
                anomaly_engine.summarise_anomalies(anomalies)
                if anomaly_engine is not None
                else f"Found {len(anomalies)} anomalies."
            )
        assistant = {
            "role": "assistant",
            "content": summary,
            "message_type": "anomaly",
            "data": {
                "anomalies": anomalies,
                "narration": {
                    "narrative_text": summary,
                    "headline": "Anomaly Report",
                    "key_findings": [],
                },
            },
        }
    else:
        with st.spinner("⚡ Thinking..."):
            out = run_query(working_df, q)
            if isinstance(out, tuple) and len(out) == 4:
                df_result, sql, err, evidence = out
            else:
                df_result, sql, err = out[0], out[1], out[2]
                evidence = None

        if err:
            assistant = {
                "role": "assistant",
                "content": str(err),
                "message_type": "error",
                "data": {
                    "error": err,
                    "error_type": "out_of_scope" if "out_of_scope" in str(err).lower() else "query",
                    "suggestions": _safe_suggested_questions(working_df),
                    "sql": sql,
                },
            }
        else:
            narration = _safe_narration(df_result, q, None, evidence)
            # Force auto-narrate decision based on user question
            if narration_engine is not None and narration_engine.should_auto_narrate(q):
                if narration is None:
                    narration = {"headline": "Analysis", "narrative_text": "", "key_findings": []}
            assistant = {
                "role": "assistant",
                "content": (narration or {}).get("summary", "Here are the results."),
                "message_type": "query",
                "data": {
                    "result_df": df_result,
                    "sql": sql,
                    "evidence": evidence,
                    "narration": narration,
                    "source_question": q,
                },
            }

    assistant["timestamp"] = datetime.now().strftime("%H:%M")
    assistant["narration_active"] = narration_on
    assistant["display_mode"] = view_mode
    st.session_state.chat_messages.append(assistant)
    st.rerun()


# ─────────────────────────────────────────────────────────────
# Mode: Ask a Question
# ─────────────────────────────────────────────────────────────

def render_ask_mode(working_df, tables, dfs):
    st.session_state["_last_working_df"] = working_df

    # Proactive insights
    insights = _safe_proactive_insights(working_df)
    if insights:
        with st.expander(f"💡 {len(insights)} Proactive Insights Found", expanded=False):
            for i, insight in enumerate(insights[:3]):
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(f"**{insight['title']}** — {insight['summary']}")
                with c2:
                    if st.button("Ask", key=f"ask_insight_{i}"):
                        st.session_state["prefill_question"] = insight["suggested_question"]
                        st.rerun()

    # Conversation banner
    conv = get_state()
    prior = conv.get("continued_from") or (
        conv.get("last_question") if conv.get("is_followup") else None
    )
    if conv.get("is_followup") and prior:
        st.markdown(
            f"<div class='conv-context-banner'>↩ Continuing from: "
            f"<em>{html.escape(str(prior))}</em></div>",
            unsafe_allow_html=True,
        )

    prefill = st.session_state.pop("prefill_question", "")
    col_input, col_btn = st.columns([9, 1])
    with col_input:
        # Use session key carefully with prefill
        if prefill:
            st.session_state["ask_question_input"] = prefill
        question = st.text_input(
            "Ask a question",
            placeholder="e.g. Show revenue by colour for 2023 | What if sales increased by 20%?",
            label_visibility="collapsed",
            key="ask_question_input",
        )
    with col_btn:
        run_btn = st.button("▶", type="primary", use_container_width=True, key="ask_run_btn")

    suggestions = _safe_suggested_questions(working_df, limit=4)
    if suggestions:
        cols = st.columns(len(suggestions))
        for i, (col, sug) in enumerate(zip(cols, suggestions)):
            with col:
                label = sug[:35] + "..." if len(sug) > 35 else sug
                if st.button(label, key=f"sug_chip_{i}", use_container_width=True):
                    st.session_state["prefill_question"] = sug
                    st.rerun()

    if not ((run_btn or False) and question and question.strip()):
        # Keep prior ask result visible if stored
        if st.session_state.get("ask_last_bundle"):
            _render_ask_result_bundle(st.session_state["ask_last_bundle"], working_df)
        return

    start_time = time.time()
    q = question.strip()

    with st.status("⚡ Processing...", expanded=True) as status:
        if detect_oob(q):
            status.update(label="🚫 Out of scope", state="error")
            st.markdown(
                """
                <div class='oob-card'>
                  <strong style='color:#fca5a5;'>🚫 Out of Scope</strong>
                  <p style='color:#cbd5e1;font-size:13px;margin:6px 0 0;'>
                    That question is outside what I can answer from this dataset.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        if _safe_whatif_detect(q) and whatif_engine is not None:
            status.update(label="🔍 What-If scenario detected...")
            scenario = whatif_engine.parse_scenario(q)
            status.update(label="⚙️ Running scenario simulation...")
            whatif_result = whatif_engine.run_scenario(working_df, scenario)
            status.update(label="✅ Scenario complete", state="complete", expanded=False)
            elapsed = round(time.time() - start_time, 2)
            st.markdown(
                f"""
                <div class='result-header-bar'>
                  <span class='badge-deterministic'>🔍 What-If Analysis</span>
                  <span class='result-stat-pill'>⏱ {elapsed}s</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_whatif_card(whatif_result)
            return

        is_anomaly_q = any(
            tok in q.lower()
            for tok in [
                "anomaly", "anomalies", "unusual", "outlier",
                "what's wrong", "flag", "anything strange",
                "stands out", "what stands out", "anything odd",
            ]
        )
        if is_anomaly_q:
            status.update(label="⚠️ Scanning for anomalies...")
            anomalies = _safe_anomaly_detect(working_df)
            summary = (
                anomaly_engine.summarise_anomalies(anomalies)
                if anomaly_engine is not None
                else f"Found {len(anomalies)} anomalies."
            )
            status.update(
                label=f"✅ Found {len(anomalies)} anomalies",
                state="complete",
                expanded=False,
            )
            elapsed = round(time.time() - start_time, 2)
            st.markdown(
                f"""
                <div class='result-header-bar'>
                  <span class='badge-fallback'>⚠️ Anomaly Report</span>
                  <span class='result-stat-pill'>{len(anomalies)} found</span>
                  <span class='result-stat-pill'>⏱ {elapsed}s</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class='narration-card'>
                  <div class='narration-headline'>⚠️ Anomaly Summary</div>
                  <div class='narration-body'>{html.escape(summary)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_anomaly_cards(anomalies, working_df=None)
            return

        status.update(label="💾 Checking cache...")
        out = run_query(working_df, q, status=status)
        if isinstance(out, tuple) and len(out) == 4:
            result_df, sql, err, evidence = out
        else:
            result_df, sql, err = out[0], out[1], out[2]
            evidence = None
        elapsed = round(time.time() - start_time, 2)

        if err:
            status.update(label="❌ Query failed", state="error", expanded=False)
            st.markdown(
                f"""
                <div class='chat-error-card'>
                  <strong style='color:#fca5a5;'>❌ Could not answer that</strong>
                  <p style='color:#cbd5e1;font-size:13px;margin:6px 0 0;'>
                    {html.escape(str(err))}
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            suggestions = _similar_question_suggestions(q)
            if suggestions:
                st.markdown("**Try one of these instead:**")
                for i, s in enumerate(suggestions):
                    if st.button(s, key=f"err_sug_{i}"):
                        st.session_state["prefill_question"] = s
                        st.rerun()
            return

        status.update(label="✅ Done", state="complete", expanded=False)

    bundle = {
        "result_df": result_df,
        "sql": sql,
        "err": err,
        "evidence": evidence,
        "elapsed": elapsed,
        "question": q,
    }
    st.session_state["ask_last_bundle"] = bundle
    _render_ask_result_bundle(bundle, working_df)


def _render_ask_result_bundle(bundle: dict, working_df):
    result_df = bundle.get("result_df")
    sql = bundle.get("sql")
    evidence = bundle.get("evidence")
    elapsed = bundle.get("elapsed", 0)
    question = bundle.get("question", "")

    if result_df is None or (isinstance(result_df, pd.DataFrame) and result_df.empty):
        st.warning("⚠️ Query returned no rows.")
        if sql:
            with st.expander("🔍 Generated SQL"):
                st.code(sql, language="sql")
        return

    badge = get_execution_badge(evidence) if evidence else BADGE_FALLBACK
    css = _badge_css_class(badge, evidence)
    row_count = len(result_df)
    metric_info = ""
    if evidence and evidence.get("resolution_source") in ("registry", "synonym"):
        metric_info = "<span class='metric-info-pill'>📐 Registry resolved</span>"

    st.markdown(
        f"""
        <div class='result-header-bar'>
          <span class='{css}'>{badge.get('icon','')} {html.escape(badge.get('label',''))}</span>
          <span class='result-stat-pill'>📋 {row_count:,} rows</span>
          <span class='result-stat-pill'>⏱ {elapsed}s</span>
          {metric_info}
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_table, tab_chart, tab_insights = st.tabs(["📊 Table", "📈 Chart", "💡 Insights"])

    with tab_table:
        st.dataframe(
            result_df,
            use_container_width=True,
            height=min(400, 40 + max(len(result_df), 1) * 35),
        )
        st.download_button(
            "⬇️ Download CSV",
            data=result_df.to_csv(index=False).encode(),
            file_name="query_result.csv",
            mime="text/csv",
            use_container_width=True,
            key="ask_dl_csv",
        )

    with tab_chart:
        try:
            all_cols = list(result_df.columns)
            num_cols = result_df.select_dtypes(include="number").columns.tolist()
            str_cols = result_df.select_dtypes(exclude="number").columns.tolist()
            auto_ct = auto_chart_type(result_df, question)
            chart_type = st.selectbox(
                "Chart Type",
                ["Bar", "Line", "Pie", "Scatter", "Area"],
                index=["Bar", "Line", "Pie", "Scatter", "Area"].index(auto_ct),
                key="ask_ct_sel",
            )
            default_x = str_cols[0] if str_cols else all_cols[0]
            default_y = num_cols[0] if num_cols else (all_cols[1] if len(all_cols) > 1 else all_cols[0])
            x_axis = st.selectbox("X Axis", all_cols, index=all_cols.index(default_x), key="ask_xa")
            y_axis = st.selectbox("Y Axis", all_cols, index=all_cols.index(default_y), key="ask_ya")
            build_chart(result_df, chart_type, x_axis, y_axis)
        except Exception:
            st.info("Chart not available for this result")

    with tab_insights:
        try:
            narration = _safe_narration(result_df, question, None, evidence)
            render_narration_card(narration)
            insights = _safe_proactive_insights(working_df)
            if insights:
                st.markdown("---")
                st.markdown("**💡 You might also want to know:**")
                for i, insight in enumerate(insights[:2]):
                    st.markdown(f"• **{insight['title']}** — {insight['summary']}")
                    if st.button(
                        f"→ {insight['suggested_question']}",
                        key=f"insight_followup_{i}",
                    ):
                        st.session_state["prefill_question"] = insight["suggested_question"]
                        st.rerun()
        except Exception:
            st.info("Insights not available for this result")

    with st.expander("🔍 Query Details"):
        if evidence:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Execution Path:** `{evidence.get('execution_path', '')}`")
                st.markdown(f"**Query Hash:** `{evidence.get('query_hash', '')}`")
                st.markdown(f"**Row Count:** `{evidence.get('result_row_count', 0)}`")
            with c2:
                st.markdown(f"**Timestamp:** `{evidence.get('timestamp', '')}`")
                st.markdown(f"**Status:** `{evidence.get('execution_status', '')}`")
                st.markdown(f"**Resolution:** `{evidence.get('resolution_source', '')}`")
        st.markdown("**SQL Used:**")
        st.code(sql or "", language="sql")


# ─────────────────────────────────────────────────────────────
# Mode: Chat with Data
# ─────────────────────────────────────────────────────────────

def render_chat_mode(working_df, tables, dfs):
    st.session_state["_last_working_df"] = working_df
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_narration_on" not in st.session_state:
        st.session_state.chat_narration_on = True
    if "chat_view_mode" not in st.session_state:
        st.session_state.chat_view_mode = "Both"

    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 4, 2])
    with ctrl_col1:
        narration_on = st.toggle(
            "📖 Narration",
            value=st.session_state.chat_narration_on,
            key="chat_narration_toggle",
            help="ON: explain results in plain English. OFF: data table only.",
        )
        if narration_on != st.session_state.chat_narration_on:
            st.session_state.chat_narration_on = narration_on
            if narration_on:
                st.toast("✨ Narration enabled — I'll explain results in plain English", icon="📖")
            else:
                st.toast("📊 Narration off — showing data only", icon="📊")

    with ctrl_col2:
        if narration_on:
            view_mode = st.radio(
                "View",
                ["Table", "Narrative", "Both"],
                horizontal=True,
                index=["Table", "Narrative", "Both"].index(
                    st.session_state.chat_view_mode
                    if st.session_state.chat_view_mode in ("Table", "Narrative", "Both")
                    else "Both"
                ),
                key="chat_view_radio",
                label_visibility="collapsed",
            )
            st.session_state.chat_view_mode = view_mode
        else:
            st.session_state.chat_view_mode = "Table"

    with ctrl_col3:
        if st.button("🗑 Clear Chat", use_container_width=True, key="clear_chat_btn"):
            st.session_state.chat_messages = []
            clear_state()
            st.toast("Chat cleared", icon="🗑")
            st.rerun()

    chat_container = st.container(height=520)
    with chat_container:
        if not st.session_state.chat_messages:
            insights = _safe_proactive_insights(working_df)
            st.markdown(
                """
                <div class='chat-welcome-card'>
                  <div class='chat-welcome-title'>👋 Hi! I've analysed your data.</div>
                  <div class='chat-welcome-subtitle'>
                    Here's what I found — click any insight to explore
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            icon_map = {
                "top_performer": "🏆",
                "trend": "📈",
                "drop": "📉",
                "concentration": "🎯",
                "growth": "🚀",
                "outlier": "⚠️",
            }
            for i, insight in enumerate(insights[:5]):
                icon = icon_map.get(insight.get("type", ""), "💡")
                direction_colour = (
                    "#6ee7b7" if insight.get("direction") == "up"
                    else "#fca5a5" if insight.get("direction") == "down"
                    else "#94a3b8"
                )
                col_ins, col_btn = st.columns([5, 1])
                with col_ins:
                    st.markdown(
                        f"""
                        <div class='proactive-insight-card'>
                          <div class='proactive-insight-icon'>{icon}</div>
                          <div style='flex:1;'>
                            <div class='proactive-insight-title'>
                              {html.escape(str(insight.get('title','')))}
                            </div>
                            <div class='proactive-insight-summary' style='color:{direction_colour};'>
                              {html.escape(str(insight.get('summary','')))}
                            </div>
                          </div>
                          <div class='proactive-ask-arrow'>Ask →</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_btn:
                    if st.button("→", key=f"welcome_insight_{i}", use_container_width=True):
                        process_chat_message(insight["suggested_question"], working_df)

            suggestions = _safe_suggested_questions(working_df, limit=4)
            if suggestions:
                st.markdown(
                    "<div style='margin-top:12px;font-size:11px;color:#64748b;margin-bottom:6px;'>"
                    "Or try one of these:</div>",
                    unsafe_allow_html=True,
                )
                sug_cols = st.columns(min(len(suggestions), 2))
                for i, sug in enumerate(suggestions):
                    with sug_cols[i % 2]:
                        if st.button(f"💬 {sug}", key=f"welcome_sug_{i}", use_container_width=True):
                            process_chat_message(sug, working_df)
        else:
            for msg in st.session_state.chat_messages:
                if msg["role"] == "user":
                    render_user_bubble(msg)
                else:
                    render_assistant_bubble(
                        msg,
                        narration_on=st.session_state.chat_narration_on,
                        view_mode=st.session_state.chat_view_mode,
                        working_df=working_df,
                    )

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    qa1, qa2, qa3 = st.columns([1, 1, 1])
    with qa1:
        if st.button("💡 Suggestions", use_container_width=True, key="chat_suggest_btn"):
            st.session_state["show_chat_suggestions"] = True
    with qa2:
        if st.button("🔍 What-If", use_container_width=True, key="chat_whatif_btn"):
            st.session_state["chat_input_prefill"] = "What if revenue increased by 20%?"
            st.toast("Prefill ready — paste or type your what-if below", icon="🔍")
    with qa3:
        if st.button("⚠️ Anomalies", use_container_width=True, key="chat_anomaly_btn"):
            process_chat_message("Find anomalies in my data", working_df)

    if st.session_state.get("show_chat_suggestions"):
        suggestions = _safe_suggested_questions(working_df, limit=6)
        with st.expander("💡 Suggested Questions", expanded=True):
            for i, sug in enumerate(suggestions):
                if st.button(sug, key=f"chat_sug_{i}", use_container_width=True):
                    st.session_state["show_chat_suggestions"] = False
                    process_chat_message(sug, working_df)

    prefill = st.session_state.pop("chat_input_prefill", None)
    if prefill:
        st.caption(f"Suggested: `{prefill}`")
        if st.button("Send suggested what-if", key="send_prefill_whatif"):
            process_chat_message(prefill, working_df)

    question = st.chat_input(
        "💬 Ask anything about your data... (try: 'why', 'what if', 'show me', 'explain')",
        key="chat_main_input",
    )
    if question and question.strip():
        process_chat_message(question, working_df)


# ─────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────

def render(working_df, tables, dfs):
    if working_df is None or working_df.empty:
        st.warning("⚠️ No data available.")
        st.stop()

    st.markdown(
        """
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
          <div>
            <div style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:1.5px;
                        text-transform:uppercase;margin-bottom:2px;">⚡ AI QUERY ENGINE</div>
            <div style="font-size:13px;color:#64748b;">Ask questions or chat with your data</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "",
        options=["🔍 Ask a Question", "💬 Chat with Data"],
        horizontal=True,
        key="query_mode_selector",
        label_visibility="collapsed",
    )
    st.markdown(
        "<hr style='border:none;border-top:1px solid rgba(99,102,241,0.1);margin:8px 0 16px;'>",
        unsafe_allow_html=True,
    )

    if mode == "🔍 Ask a Question":
        render_ask_mode(working_df, tables, dfs)
    else:
        render_chat_mode(working_df, tables, dfs)
