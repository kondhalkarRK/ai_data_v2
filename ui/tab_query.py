"""
ui/tab_query.py
Semantic-first Query + Chat UI (Master Prompt Sections 5–6).
"""
from __future__ import annotations

import html
import time
from datetime import datetime

import pandas as pd
import streamlit as st

from core.nlq_engine import run_query, run_sql
from core.sql_guardrails import sql_is_safe
from core.chart_engine import auto_chart_type, build_chart
from core.llm_client import call_llm

try:
    from core.conversation_state import (
        get_state,
        clear_state,
        is_data_question,
        build_chat_context_string,
        append_chat_exchange,
    )
except Exception:
    def get_state():
        return st.session_state.get("conversation_state") or {}

    def clear_state():
        st.session_state.conversation_state = {}

    def is_data_question(q, df=None):
        return True

    def build_chat_context_string(n=5):
        return ""

    def append_chat_exchange(*args, **kwargs):
        pass

try:
    from core.question_normaliser import detect_oob
except Exception:
    def detect_oob(q):
        return False

try:
    from core.evidence_builder import get_execution_badge
except Exception:
    def get_execution_badge(evidence):
        return {"icon": "⚠️", "label": "AI Generated", "colour": "orange"}

try:
    from features.whatif_engine import WhatIfEngine
    whatif_engine = WhatIfEngine()
except Exception:
    whatif_engine = None

try:
    from features.narration_engine import NarrationEngine
    narration_engine = NarrationEngine()
except Exception:
    narration_engine = None

try:
    from features.proactive_engine import ProactiveEngine
    proactive_engine = ProactiveEngine()
except Exception:
    proactive_engine = None


def _safe_insights(df, limit=4):
    if proactive_engine is None:
        return []
    try:
        return proactive_engine.generate_proactive_insights(df, limit=limit)
    except Exception:
        return []


def _safe_narration(df, question, evidence=None):
    if narration_engine is None:
        return None
    try:
        return narration_engine.generate_narration(df, question, evidence=evidence)
    except Exception:
        return None


def _badge_class(evidence):
    path = (evidence or {}).get("execution_path", "fallback")
    return {
        "deterministic": "badge-deterministic",
        "cache": "badge-cached",
        "fallback": "badge-fallback",
        "semantic": "badge-semantic",
    }.get(path, "badge-fallback")


def _render_semantic_layer_status(question: str = ""):
    """Show resolved glossary terms + injection summary (semantic_prompt Task 4)."""
    matches = st.session_state.get("last_glossary_matches") or []
    hints = st.session_state.get("last_glossary_hints") or ""
    rules = st.session_state.get("last_domain_rules") or ""
    sem_ctx = st.session_state.get("last_semantic_context") or ""

    resolved_count = len(matches)
    hints_active = bool(str(hints).strip())
    rules_active = bool(str(rules).strip())
    detail_parts = []
    if resolved_count:
        detail_parts.append(f"{resolved_count} terms resolved")
    if hints_active:
        detail_parts.append("SQL hints active")
    if rules_active:
        detail_parts.append("domain rules active")
    detail_str = " · ".join(detail_parts)

    st.markdown(
        f"<div style='font-size:11px;color:#94a3b8;margin-bottom:6px;'>"
        f"🧠 <b style='color:#a5b4fc;'>Semantic layer active</b>"
        f"{(' — ' + detail_str) if detail_str else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )

    if matches:
        badges = []
        for m in matches[:5]:
            label = html.escape(str(m.get("term_name") or m.get("matched_token") or ""))
            expr = m.get("sql_expression") or m.get("source_column") or ""
            expr_s = " ".join(str(expr).split())
            title = html.escape(f"{label} = {expr_s}" if expr_s else label)
            if expr_s and len(expr_s) <= 40:
                badges.append(
                    f"<span class='sem-term-badge' title='{title}'>"
                    f"{label}"
                    f"<span style='opacity:0.55;font-size:9px;margin-left:4px;'>"
                    f"= {html.escape(expr_s)}</span></span>"
                )
            else:
                badges.append(
                    f"<span class='sem-term-badge' title='{title}'>{label}</span>"
                )
        st.markdown(" ".join(badges), unsafe_allow_html=True)

    with st.expander("🧠 Semantic Context Injected", expanded=False):
        st.markdown("**What the AI received from semantic layer:**")
        if str(sem_ctx).strip():
            st.markdown("✅ Business model context injected")
        if hints_active:
            st.markdown("✅ SQL hints from glossary injected")
            st.code(hints, language="")
        if rules_active:
            st.markdown("✅ Domain rules injected")
        if not (sem_ctx or hints or rules):
            st.markdown(
                "⚠️ Semantic layer inactive — check semantic YAML files"
            )
        st.caption(f"{resolved_count} business terms resolved from your question")
        if question:
            st.caption(f"Question: {question}")


def render_narration_card(narration: dict | None):
    if not narration:
        return
    headline = html.escape(str(narration.get("headline") or "Insight"))
    body = html.escape(str(narration.get("narrative_text") or narration.get("summary") or ""))
    st.markdown(
        f"""
        <div class="narration-card">
          <div class="narration-headline">📊 {headline}</div>
          <div class="narration-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    findings = narration.get("key_findings") or []
    if findings:
        for f in findings:
            st.markdown(f"• {f}")
    if narration.get("recommendation"):
        st.markdown(
            f'<div class="narration-recommendation">💡 {html.escape(str(narration["recommendation"]))}</div>',
            unsafe_allow_html=True,
        )


def render_editable_sql(sql: str, working_df, result_key: str = "ask_custom_result"):
    """Editable SQL panel below results — custom runs do not update cache/conversation."""
    st.markdown("---")
    st.markdown("##### ✏️ Edit SQL & Re-run")
    edited = st.text_area(
        "✏️ SQL (editable)",
        value=(sql or "").strip(),
        height=120,
        key="editable_sql",
    )
    st.caption("Tip: Edit the SQL above and click Run to customise your query")
    if st.button("▶ Run Custom SQL", key="run_custom_sql_btn"):
        custom_sql = (edited or "").strip()
        safe, reason = sql_is_safe(custom_sql)
        if not safe:
            st.error(f"🔒 Blocked: {reason}")
            return
        new_result, new_err = run_sql(custom_sql, working_df)
        if new_err:
            st.error(f"SQL error: {new_err}")
        elif new_result is not None:
            st.session_state[result_key] = {
                "result_df": new_result,
                "sql": custom_sql,
                "custom": True,
            }
            st.rerun()


# ── Ask / Query mode ─────────────────────────────────────────────

def render_ask_mode(working_df, tables, dfs):
    st.session_state["_last_working_df"] = working_df

    insights = _safe_insights(working_df, limit=3)
    if insights:
        with st.expander(f"💡 {len(insights)} Proactive Insights", expanded=False):
            for ins in insights:
                st.markdown(f"**{ins.get('title','')}** — {ins.get('summary','')}")

    conv = get_state()
    prior = conv.get("continued_from")
    if conv.get("is_followup") and prior:
        st.markdown(
            f"<div class='conv-context-banner'>↩ Continuing from: "
            f"<em>{html.escape(str(prior))}</em></div>",
            unsafe_allow_html=True,
        )

    col_in, col_btn = st.columns([9, 1])
    with col_in:
        question = st.text_input(
            "Ask a question",
            placeholder="e.g. Show revenue by colour for 2023 | What if sales increased by 20%?",
            label_visibility="collapsed",
            key="ask_question_input",
        )
    with col_btn:
        run_btn = st.button("▶", type="primary", use_container_width=True, key="ask_run_btn")

    # Show custom SQL override if present
    custom = st.session_state.get("ask_custom_result")
    if custom and not run_btn:
        st.markdown('<span class="badge-fallback">🔧 Custom SQL</span>', unsafe_allow_html=True)
        st.dataframe(custom["result_df"], use_container_width=True)
        render_editable_sql(custom.get("sql", ""), working_df)
        return

    if st.session_state.get("ask_last_bundle") and not (run_btn and question and question.strip()):
        _render_ask_bundle(st.session_state["ask_last_bundle"], working_df)
        return

    if not (run_btn and question and question.strip()):
        return

    q = question.strip()
    start = time.time()
    st.session_state.pop("ask_custom_result", None)

    with st.status("⚡ Processing...", expanded=True) as status:
        if detect_oob(q):
            status.update(label="🚫 Out of scope", state="error")
            st.markdown(
                """
                <div class="oob-card">
                  <strong style="color:#fca5a5;">🚫 Out of Scope</strong>
                  <p style="color:#cbd5e1;font-size:13px;margin:6px 0 0;">
                    That question is outside what I can answer from this dataset.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        if whatif_engine is not None and whatif_engine.detect_whatif_query(q):
            status.update(label="🔍 What-If scenario...")
            scenario = whatif_engine.parse_scenario(q, working_df)
            result = whatif_engine.run_scenario(working_df, scenario)
            st.session_state["whatif_last_result"] = result
            st.session_state["whatif_last_scenario"] = scenario
            status.update(label="✅ Scenario complete", state="complete", expanded=False)
            whatif_engine.generate_interactive_result(result, q, working_df, scenario)
            return

        status.update(label="🧭 Resolving with semantic layer...")
        out = run_query(working_df, q, status=status)
        if isinstance(out, tuple) and len(out) == 4:
            result_df, sql, err, evidence = out
        else:
            result_df, sql, err = out[0], out[1], out[2]
            evidence = None
        elapsed = round(time.time() - start, 2)

        if err:
            status.update(label="❌ Failed", state="error", expanded=False)
            st.error(err)
            return

        status.update(label="✅ Done", state="complete", expanded=False)

    bundle = {
        "result_df": result_df,
        "sql": sql,
        "evidence": evidence,
        "elapsed": elapsed,
        "question": q,
    }
    st.session_state["ask_last_bundle"] = bundle
    _render_ask_bundle(bundle, working_df)


def _render_ask_bundle(bundle, working_df):
    result_df = bundle.get("result_df")
    sql = bundle.get("sql")
    evidence = bundle.get("evidence")
    elapsed = bundle.get("elapsed", 0)
    question = bundle.get("question", "")

    if result_df is None or (isinstance(result_df, pd.DataFrame) and result_df.empty):
        st.warning("⚠️ Query returned no rows.")
        if sql:
            with st.expander("SQL"):
                st.code(sql, language="sql")
        return

    badge = get_execution_badge(evidence) if evidence else {"icon": "⚠️", "label": "AI Generated"}
    css = _badge_class(evidence)
    st.markdown(
        f"""
        <div class="result-header-bar">
          <span class="{css}">{badge.get('icon','')} {html.escape(badge.get('label',''))}</span>
          <span class="result-stat-pill">📋 {len(result_df):,} rows</span>
          <span class="result-stat-pill">⏱ {elapsed}s</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_semantic_layer_status(question)

    tab_table, tab_chart, tab_insights = st.tabs(["📊 Table", "📈 Chart", "💡 Insights"])
    with tab_table:
        st.dataframe(result_df, use_container_width=True)
        st.download_button(
            "⬇️ Download CSV",
            data=result_df.to_csv(index=False).encode(),
            file_name="query_result.csv",
            mime="text/csv",
            key="ask_dl",
        )
    with tab_chart:
        try:
            cols = list(result_df.columns)
            nums = result_df.select_dtypes(include="number").columns.tolist()
            strs = result_df.select_dtypes(exclude="number").columns.tolist()
            ct = auto_chart_type(result_df, question)
            chart_type = st.selectbox(
                "Chart Type", ["Bar", "Line", "Pie", "Scatter", "Area"],
                index=["Bar", "Line", "Pie", "Scatter", "Area"].index(ct),
                key="ask_chart_type",
            )
            x = st.selectbox("X", cols, index=cols.index(strs[0] if strs else cols[0]), key="ask_x")
            y = st.selectbox("Y", cols, index=cols.index(nums[0] if nums else cols[-1]), key="ask_y")
            build_chart(result_df, chart_type, x, y)
        except Exception:
            st.info("Chart not available")
    with tab_insights:
        narr = _safe_narration(result_df, question, evidence)
        render_narration_card(narr)

    with st.expander("🔍 Query Details"):
        if evidence:
            st.markdown(f"**Path:** `{evidence.get('execution_path')}`")
            st.markdown(f"**Hash:** `{evidence.get('query_hash')}`")
            st.markdown(f"**Resolution:** `{evidence.get('resolution_source')}`")
        st.code(sql or "", language="sql")

    render_editable_sql(sql or "", working_df)


# ── Chat mode ────────────────────────────────────────────────────

def _conversational_reply(question: str, working_df: pd.DataFrame | None = None) -> str:
    history = ""
    try:
        history = build_chat_context_string(5)
    except Exception:
        history = ""

    data_summary = ""
    if working_df is not None and not working_df.empty:
        cols = ", ".join(str(c) for c in list(working_df.columns)[:18])
        data_summary = (
            f"Dataset loaded: {len(working_df):,} rows, "
            f"{len(working_df.columns)} columns ({cols}"
            f"{'…' if len(working_df.columns) > 18 else ''})."
        )

    glossary_bits = ""
    try:
        from semantic.semantic_loader import get_semantic_loader
        loader = get_semantic_loader()
        matches = loader.get_glossary_hints_for_question(question)
        if matches:
            parts = []
            for m in matches[:4]:
                expr = m.get("sql_expression") or m.get("source_column") or ""
                parts.append(f"{m.get('term_name')}: {expr}")
            glossary_bits = "Relevant business terms: " + "; ".join(parts)
    except Exception:
        glossary_bits = ""

    prompt = f"""You are a helpful AI data assistant embedded in an analytics platform.
Respond naturally and helpfully. Keep responses concise (2-4 sentences).

Capabilities you can describe:
- Answer natural-language questions about the uploaded sales dataset
- Resolve business terms (Revenue, Units Sold, Colour, etc.) via a semantic glossary
- Run what-if scenarios ("what if revenue increased 20%")
- Explain results and trends in plain language
- Follow-ups like "same but for 2023" or "tell me more"

{data_summary}
{glossary_bits}

{history}

User: {question}
Assistant:"""
    text = call_llm(prompt)
    return (text or "Hi! Ask me anything about your uploaded data — revenue, colours, makes, trends.").strip()


def _should_force_narration(question: str) -> bool:
    q = (question or "").lower()
    return any(
        p in q
        for p in (
            "why", "explain", "how come", "what caused", "tell me more",
            "insight", "interpret", "meaning",
        )
    )


def _chat_scroll_to_bottom():
    """Scroll the chat message panel to the latest message."""
    try:
        import streamlit.components.v1 as components
        components.html(
            """
            <script>
            (function() {
              const doc = window.parent.document;
              // Prefer our marked chat scroll area
              let box = doc.querySelector('[data-testid="stVerticalBlockBorderWrapper"]');
              const anchors = doc.querySelectorAll('#chat-scroll-anchor');
              if (anchors.length) {
                const a = anchors[anchors.length - 1];
                a.scrollIntoView({behavior: 'smooth', block: 'end'});
                // Also scroll nearest scrollable parent
                let p = a.parentElement;
                for (let i = 0; i < 8 && p; i++) {
                  if (p.scrollHeight > p.clientHeight + 40) {
                    p.scrollTop = p.scrollHeight;
                    break;
                  }
                  p = p.parentElement;
                }
                return;
              }
              if (box) box.scrollTop = box.scrollHeight;
            })();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def process_chat_message(question: str, working_df: pd.DataFrame):
    if not question or not str(question).strip() or working_df is None:
        return
    q = question.strip()
    now = datetime.now().strftime("%H:%M")
    st.session_state.setdefault("chat_messages", [])
    st.session_state.chat_messages.append({
        "role": "user",
        "content": q,
        "timestamp": now,
        "message_type": "chat",
        "data": {},
    })

    narration_on = st.session_state.get("chat_narration_on", True)

    if detect_oob(q):
        assistant = {
            "role": "assistant",
            "content": "That question is outside what I can answer from this dataset.",
            "message_type": "error",
            "data": {},
            "timestamp": datetime.now().strftime("%H:%M"),
        }
        st.session_state.chat_messages.append(assistant)
        st.rerun()
        return

    # Conversational (non-data)
    if not is_data_question(q, working_df):
        with st.spinner("💬 Thinking..."):
            reply = _conversational_reply(q, working_df)
        append_chat_exchange(q, result_summary=None, was_data_query=False)
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": reply,
            "message_type": "chat",
            "data": {},
            "timestamp": datetime.now().strftime("%H:%M"),
        })
        st.rerun()
        return

    # What-if
    if whatif_engine is not None and whatif_engine.detect_whatif_query(q):
        with st.spinner("🔍 Running scenario..."):
            scenario = whatif_engine.parse_scenario(q, working_df)
            result = whatif_engine.run_scenario(working_df, scenario)
        append_chat_exchange(q, result_summary=result.get("narrative"), was_data_query=True)
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": result.get("narrative", "Scenario complete."),
            "message_type": "whatif",
            "data": {"whatif_result": result, "scenario": scenario},
            "timestamp": datetime.now().strftime("%H:%M"),
        })
        st.rerun()
        return

    # Data query
    with st.spinner("⚡ Querying your data with semantic layer..."):
        out = run_query(working_df, q)
        if isinstance(out, tuple) and len(out) == 4:
            df_result, sql, err, evidence = out
        else:
            df_result, sql, err = out[0], out[1], out[2]
            evidence = None

    if err:
        st.session_state.chat_messages.append({
            "role": "assistant",
            "content": str(err),
            "message_type": "error",
            "data": {"sql": sql},
            "timestamp": datetime.now().strftime("%H:%M"),
        })
        st.rerun()
        return

    force = _should_force_narration(q)
    narr = _safe_narration(df_result, q, evidence)
    summary = (narr or {}).get("result_summary") or (
        f"{len(df_result)} rows returned" if isinstance(df_result, pd.DataFrame) else "Done"
    )
    append_chat_exchange(q, result_summary=summary, was_data_query=True)

    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": (narr or {}).get("summary", "Here are the results."),
        "message_type": "query",
        "data": {
            "result_df": df_result,
            "sql": sql,
            "evidence": evidence,
            "narration": narr,
            "result_summary": summary,
            "force_narration": force or narration_on,
            "source_question": q,
            "glossary_matches": list(st.session_state.get("last_glossary_matches") or []),
        },
        "timestamp": datetime.now().strftime("%H:%M"),
    })
    st.rerun()


def render_user_bubble(msg):
    st.markdown(
        f"""
        <div class="user-bubble">
          <div class="user-bubble-text">{html.escape(str(msg.get('content','')))}</div>
          <div class="user-avatar">👤</div>
        </div>
        <div class="msg-timestamp-right">{html.escape(str(msg.get('timestamp','')))}</div>
        """,
        unsafe_allow_html=True,
    )


def render_assistant_bubble(msg, working_df, narration_on: bool):
    data = msg.get("data") or {}
    mtype = msg.get("message_type", "chat")
    st.markdown(
        """
        <div class="assistant-bubble">
          <div class="assistant-avatar">🤖</div>
          <div class="assistant-card">
        """,
        unsafe_allow_html=True,
    )

    if mtype in ("chat", "error"):
        st.markdown(html.escape(str(msg.get("content", ""))))
    elif mtype == "whatif":
        result = data.get("whatif_result") or {}
        scenario = data.get("scenario") or {}
        if whatif_engine is not None and result:
            whatif_engine.generate_interactive_result(
                result, msg.get("content", ""), working_df, scenario
            )
        else:
            st.markdown(html.escape(str(msg.get("content", ""))))
    elif mtype == "query":
        evidence = data.get("evidence")
        badge = get_execution_badge(evidence) if evidence else {"icon": "🧠", "label": "Semantic + AI"}
        st.markdown(
            f'<span class="{_badge_class(evidence)}">{badge.get("icon","")} '
            f'{html.escape(badge.get("label",""))}</span>',
            unsafe_allow_html=True,
        )
        matches = data.get("glossary_matches") or []
        if matches:
            chips = []
            for m in matches[:4]:
                label = html.escape(str(m.get("term_name") or ""))
                expr = m.get("sql_expression") or m.get("source_column") or ""
                expr_s = html.escape(" ".join(str(expr).split())[:40])
                chips.append(
                    f"<span class='sem-term-badge'>{label}"
                    + (f"<span style='opacity:0.55;font-size:9px;margin-left:4px;'>= {expr_s}</span>" if expr_s else "")
                    + "</span>"
                )
            st.markdown(" ".join(chips), unsafe_allow_html=True)
        force = data.get("force_narration") or False
        show_narr = narration_on or force
        if show_narr:
            render_narration_card(data.get("narration"))
        rdf = data.get("result_df")
        if isinstance(rdf, pd.DataFrame):
            show_n = min(10, len(rdf))
            st.dataframe(rdf.head(show_n), use_container_width=True)
            if len(rdf) > 10:
                with st.expander(f"Show all {len(rdf)} rows"):
                    st.dataframe(rdf, use_container_width=True)
        sql = data.get("sql")
        if sql and not str(sql).startswith("--"):
            with st.expander("SQL used"):
                st.code(sql, language="sql")

    st.markdown("</div></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="msg-timestamp">{html.escape(str(msg.get("timestamp","")))}</div>',
        unsafe_allow_html=True,
    )


def render_chat_mode(working_df, tables, dfs):
    st.session_state["_last_working_df"] = working_df
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("chat_narration_on", True)

    c1, c2 = st.columns([3, 2])
    with c1:
        narration_on = st.toggle(
            "📖 Narration",
            value=st.session_state.chat_narration_on,
            key="chat_narration_toggle",
        )
        st.session_state.chat_narration_on = narration_on
    with c2:
        if st.button("🗑 Clear Chat", use_container_width=True, key="clear_chat_btn"):
            st.session_state.chat_messages = []
            clear_state()
            st.toast("Chat cleared", icon="🗑")
            st.rerun()

    chat_box = st.container(height=480, border=True)
    with chat_box:
        if not st.session_state.chat_messages:
            insights = _safe_insights(working_df, limit=4)
            st.markdown(
                """
                <div class="chat-welcome-card">
                  <div class="chat-welcome-title">👋 Hi! I've analysed your data.</div>
                  <div class="chat-welcome-subtitle">Ask about revenue, colours, makes — or just say hi.
                  Follow-ups like "same for 2023" or "tell me more" work too.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for ins in insights:
                st.markdown(f"**{ins.get('title','')}** — {ins.get('summary','')}")
        else:
            for msg in st.session_state.chat_messages:
                if msg.get("role") == "user":
                    render_user_bubble(msg)
                else:
                    render_assistant_bubble(
                        msg, working_df, st.session_state.chat_narration_on
                    )
        st.markdown('<div id="chat-scroll-anchor"></div>', unsafe_allow_html=True)

    _chat_scroll_to_bottom()

    st.markdown('<div class="chat-input-area chat-input-area-visible">', unsafe_allow_html=True)
    question = st.chat_input(
        "Ask about your data, say hi, or ask a follow-up…",
        key="chat_main_input",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    if question and question.strip():
        process_chat_message(question, working_df)


# ── Entry ────────────────────────────────────────────────────────

def render(working_df, tables, dfs):
    if working_df is None or working_df.empty:
        st.warning("⚠️ No data available.")
        st.stop()

    st.markdown(
        """
        <div style="margin-bottom:12px;">
          <div style="font-size:11px;font-weight:700;color:#818cf8;letter-spacing:1.5px;
                      text-transform:uppercase;">⚡ AI QUERY ENGINE</div>
          <div style="font-size:13px;color:#94a3b8;">Semantic-powered analytics — ask or chat</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Native tabs — not the old radio mode selector
    tab_q, tab_c = st.tabs(["⚡ Query", "💬 Chat"])
    with tab_q:
        render_ask_mode(working_df, tables, dfs)
    with tab_c:
        render_chat_mode(working_df, tables, dfs)
