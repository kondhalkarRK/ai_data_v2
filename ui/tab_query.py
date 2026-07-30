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
        is_awaiting_clarification,
        set_pending_clarification,
        resolve_clarification,
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

    def is_awaiting_clarification():
        return False

    def set_pending_clarification(*args, **kwargs):
        pass

    def resolve_clarification(choice):
        return None

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
            # Heuristic badge type
            kind = "glossary"
            expr_u = (expr_s or "").upper()
            if "SUM(" in expr_u or "COUNT(" in expr_u or "/" in expr_u:
                kind = "measure"
            elif expr_s and not expr_u.startswith("COLUMN") and "(" not in expr_u:
                kind = "dimension"
            elif (expr_s or "").lower().startswith("column "):
                kind = "dimension"
            expr_html = (
                f"<span class='sem-expr'>= {html.escape(expr_s[:40])}</span>"
                if expr_s and len(expr_s) <= 40 else ""
            )
            badges.append(
                f"<span class='sem-term-badge {kind}' title='{title}'>"
                f"{label}{expr_html}</span>"
            )
        st.markdown(" ".join(badges), unsafe_allow_html=True)

    st.markdown(
        '<div class="sem-ctx-expander-hint">🧠 Semantic Context Injected</div>',
        unsafe_allow_html=True,
    )
    with st.expander("View injected context", expanded=False):
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
            st.markdown(
                f'<div class="finding-bullet">{html.escape(str(f))}</div>',
                unsafe_allow_html=True,
            )
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
        st.markdown('<div class="ask-run-btn-wrap">', unsafe_allow_html=True)
        run_btn = st.button("▶", type="primary", use_container_width=True, key="ask_run_btn")
        st.markdown("</div>", unsafe_allow_html=True)

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
    st.session_state["editable_sql"] = (sql or "").strip()  
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

    # Trust score for ask mode (chat_ench Feature 2)
    try:
        evidence = evidence or {}
        if "trust_score" not in evidence:
            ts, tb = compute_trust_score(evidence, result_df, working_df)
            evidence["trust_score"] = ts
            evidence["trust_breakdown"] = tb
            bundle["evidence"] = evidence
        render_trust_score_card(evidence)
    except Exception:
        pass

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
    st.session_state["editable_sql"] = (sql or "").strip()  
    render_editable_sql(sql or "", working_df)


# ── Chat intelligence (chat_ench.md) ──────────────────────────────

_DESTRUCTIVE_TERMS = (
    "delete", "drop", "remove data", "update", "truncate", "modify",
    "alter", "overwrite", "wipe", "destroy", "erase", "clear data",
)

_SURPRISE_PHRASES = (
    "surprise me", "surprise me!", "impress me",
    "what's interesting", "whats interesting",
    "show me something interesting",
)

_AMBIGUOUS_EXACT = (
    "show me the best", "compare them", "how is it doing",
    "what's the performance", "whats the performance",
    "how is performance", "show me the best!",
)


def detect_destructive(question: str) -> bool:
    q = (question or "").lower()
    return any(t in q for t in _DESTRUCTIVE_TERMS)


def detect_surprise_me(question: str) -> bool:
    q = (question or "").strip().lower().rstrip("!.?")
    return any(q == p.rstrip("!.?") or p in q for p in _SURPRISE_PHRASES)


def is_greeting(question: str) -> bool:
    q = (question or "").strip().lower().rstrip("!.")
    greetings = {
        "hi", "hello", "hey", "hiya", "howdy",
        "good morning", "good afternoon", "good evening",
        "morning", "afternoon", "evening",
    }
    return q in greetings or q.startswith(("hi ", "hello ", "hey "))


def detect_ambiguous(question: str) -> bool:
    q = (question or "").strip().lower().rstrip("?.!")
    if q in _AMBIGUOUS_EXACT:
        return True
    # "tell me about X" where X looks like a dimension
    if q.startswith("tell me about ") and len(q.split()) <= 5:
        rest = q.replace("tell me about ", "")
        if rest and not any(
            m in rest for m in ("revenue", "sales", "units", "orders", "trend")
        ):
            return True
    if q in ("show me the best", "compare them", "how is performance"):
        return True
    return False


def _time_of_day_greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning! 👋"
    if hour < 17:
        return "Good afternoon! 👋"
    return "Good evening! 👋"


def _suggested_qs(df: pd.DataFrame, limit: int = 2) -> list[str]:
    if proactive_engine is not None:
        try:
            qs = proactive_engine.get_suggested_questions(df, limit=limit)
            if qs:
                return qs
        except Exception:
            pass
    return ["Show revenue by colour", "Monthly revenue trend"][:limit]


def compute_trust_score(evidence, result_df, working_df) -> tuple[int, dict]:
    """Five-component Data Trust Score (0–100)."""
    matches = st.session_state.get("last_glossary_matches") or []
    hints = st.session_state.get("last_glossary_hints") or ""

    # 1 Semantic match
    n = len(matches)
    semantic = 0 if n == 0 else (10 if n == 1 else 20)

    # 2 Glossary match
    glossary = 20 if str(hints).strip() else 0
    if not glossary and matches:
        glossary = 10

    # 3 SQL validation
    path = (evidence or {}).get("execution_path", "fallback")
    if path == "semantic":
        sql_val = 20
    elif path == "cache":
        sql_val = 15
    elif path == "fallback":
        sql_val = 10
    else:
        sql_val = 5

    # 4 Row coverage
    try:
        n_res = len(result_df) if result_df is not None else 0
        n_all = max(len(working_df) if working_df is not None else 1, 1)
        ratio = n_res / n_all
        if ratio > 0.5:
            row_cov = 20
        elif ratio >= 0.10:
            row_cov = 15
        elif ratio >= 0.01:
            row_cov = 10
        elif n_res > 0:
            row_cov = 5
        else:
            row_cov = 0
    except Exception:
        row_cov = 5

    # 5 Join quality
    src = (evidence or {}).get("resolution_source", "")
    if src == "semantic_llm" or path == "semantic":
        join_q = 20
    elif path == "cache" or src == "cache":
        join_q = 15
    else:
        join_q = 5

    breakdown = {
        "semantic": semantic,
        "glossary": glossary,
        "sql_validation": sql_val,
        "row_coverage": row_cov,
        "join_quality": join_q,
    }
    return sum(breakdown.values()), breakdown


def _trust_band(score: int) -> tuple[str, str]:
    if score >= 90:
        return "Excellent", "#10b981"
    if score >= 75:
        return "High", "#6ee7b7"
    if score >= 60:
        return "Good", "#fcd34d"
    if score >= 40:
        return "Moderate", "#f97316"
    return "Low", "#ef4444"


def render_trust_score_card(evidence: dict | None):
    if not evidence or evidence.get("trust_score") is None:
        return
    score = int(evidence.get("trust_score") or 0)
    bd = evidence.get("trust_breakdown") or {}
    label, color = _trust_band(score)
    note = ""
    if score >= 100:
        note = '<div class="trust-note">🏆 Perfect data confidence</div>'
    elif score < 75:
        note = (
            '<div class="trust-note warn">⚠️ Lower confidence — review SQL '
            "for accuracy before decisions</div>"
        )

    def row(name, key):
        v = int(bd.get(key, 0))
        icon = "✅" if v >= 15 else ("🟡" if v >= 10 else "⚠️")
        return (
            f'<div class="trust-row"><span>{icon} {name}</span>'
            f"<span>{v}/20</span></div>"
        )

    st.markdown(
        f"""
        <div class="trust-score-card" style="border-color:{color}33;">
          <div class="trust-title">🎯 Data Trust Score</div>
          <div class="trust-score-line">
            <span class="trust-pct" style="color:{color};">{score}%</span>
            <span class="trust-band" style="color:{color};">{label}</span>
          </div>
          <div class="trust-bar">
            <div class="trust-bar-fill" style="width:{score}%;background:{color};"></div>
          </div>
          <div class="trust-based">Based on:</div>
          {row("Semantic match", "semantic")}
          {row("Glossary match", "glossary")}
          {row("SQL validation", "sql_validation")}
          {row("Row coverage", "row_coverage")}
          {row("Join quality", "join_quality")}
          {note}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _find_rev_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if str(c).lower() in ("total_sales", "revenue", "sales", "amount"):
            return c
    nums = df.select_dtypes(include="number").columns.tolist()
    return nums[0] if nums else None


def _find_qty_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if str(c).lower() in ("order_qty", "qty", "quantity", "units"):
            return c
    return None


def _find_date_col(df: pd.DataFrame) -> str | None:
    for c in df.columns:
        if "date" in str(c).lower():
            return c
    return None


def _categorical_cols(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("string"):
            if 1 < df[c].nunique() <= min(50, max(3, len(df) // 5)):
                out.append(c)
    return out[:8]


def run_surprise_analysis(df: pd.DataFrame) -> dict:
    """Run automated findings + LLM recommendations for Surprise Me."""
    findings: list[str] = []
    highlight = ""
    rev = _find_rev_col(df)
    qty = _find_qty_col(df)
    cats = _categorical_cols(df)
    n = len(df)

    # Step 1 — highest concentration
    if rev and cats:
        total = float(pd.to_numeric(df[rev], errors="coerce").fillna(0).sum()) or 1.0
        best_pct, best_txt = 0.0, ""
        for c in cats:
            g = df.groupby(c)[rev].apply(
                lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())
            )
            if g.empty:
                continue
            top_val = g.idxmax()
            pct = float(g.max()) / total * 100
            if pct > best_pct:
                best_pct = pct
                best_txt = f"{top_val} ({c}) = {pct:.0f}% of all revenue"
        if best_txt:
            findings.append(f"Highest concentration: {best_txt}")

    # Step 2 — best cross-segment vs avg revenue per order
    if rev and len(cats) >= 2:
        c1, c2 = cats[0], cats[1]
        tmp = df.copy()
        tmp["__rev__"] = pd.to_numeric(tmp[rev], errors="coerce").fillna(0)
        avg_rpo = float(tmp["__rev__"].sum() / max(len(tmp), 1)) or 1.0
        grp = tmp.groupby([c1, c2]).agg(
            rev=("__rev__", "sum"), n=("__rev__", "count")
        )
        grp = grp[grp["n"] >= max(2, len(tmp) // 200)]
        if not grp.empty:
            grp["rpo"] = grp["rev"] / grp["n"]
            top = grp["rpo"].idxmax()
            mult = float(grp.loc[top, "rpo"]) / avg_rpo
            highlight = (
                f"{top[0]} × {top[1]} = {mult:.1f}x avg revenue per order"
            )
            findings.append(f"Best cross-segment: {highlight}")

    # Step 3 — unexpected performer (low volume, high rev/unit)
    if rev and qty and cats:
        c = cats[0]
        tmp = df.copy()
        tmp["__rev__"] = pd.to_numeric(tmp[rev], errors="coerce").fillna(0)
        tmp["__qty__"] = pd.to_numeric(tmp[qty], errors="coerce").fillna(0)
        g = tmp.groupby(c).agg(rev=("__rev__", "sum"), qty=("__qty__", "sum"))
        g = g[g["qty"] > 0]
        if len(g) >= 3:
            g["rpu"] = g["rev"] / g["qty"]
            g["vol_rank"] = g["qty"].rank(ascending=False)
            g["rpu_rank"] = g["rpu"].rank(ascending=False)
            # low volume rank number high, rpu rank low
            cand = g[(g["vol_rank"] >= len(g) * 0.5) & (g["rpu_rank"] <= 3)]
            if cand.empty:
                cand = g.sort_values("rpu", ascending=False).head(1)
            row = cand.sort_values("rpu", ascending=False).iloc[0]
            name = cand.sort_values("rpu", ascending=False).index[0]
            findings.append(
                f"Unexpected performer: {name} ranks "
                f"{int(row['vol_rank'])}th on units but "
                f"{int(row['rpu_rank'])}nd on revenue per unit"
            )

    # Step 4 — trend anomaly
    dcol = _find_date_col(df)
    if dcol and rev:
        try:
            tmp = df.copy()
            tmp["__dt__"] = pd.to_datetime(tmp[dcol], errors="coerce")
            tmp["__rev__"] = pd.to_numeric(tmp[rev], errors="coerce").fillna(0)
            tmp = tmp.dropna(subset=["__dt__"])
            monthly = tmp.groupby(tmp["__dt__"].dt.to_period("M"))["__rev__"].sum()
            if len(monthly) >= 4:
                roll = monthly.rolling(3, min_periods=2).mean()
                dev = (monthly - roll).abs()
                worst = dev.idxmax()
                findings.append(
                    f"Trend anomaly: {worst} had the largest deviation "
                    f"from the 3-month rolling average"
                )
        except Exception:
            pass

    if not highlight and findings:
        highlight = findings[0]
    if not findings:
        findings = ["Your dataset is ready — try asking about revenue by colour or make."]
        highlight = findings[0]

    # Step 5 — LLM recommendations
    decisions = []
    opportunity = "—"
    try:
        prompt = (
            "Based on these data findings:\n"
            + "\n".join(f"- {f}" for f in findings)
            + "\nGenerate exactly 3 business decisions a sales director would make today.\n"
            "Each decision: one action sentence.\n"
            "Then estimate combined revenue opportunity as a single number.\n"
            "Format: decision | revenue_impact"
        )
        raw = call_llm(prompt) or ""
        for line in raw.splitlines():
            line = line.strip(" -•\t")
            if "|" in line:
                parts = [p.strip() for p in line.split("|", 1)]
                decisions.append(parts[0])
                if parts[1] and opportunity == "—":
                    opportunity = parts[1]
            elif line and len(decisions) < 3 and any(c.isalpha() for c in line):
                decisions.append(line.lstrip("0123456789.) "))
        decisions = [d for d in decisions if d][:3]
    except Exception:
        decisions = []

    while len(decisions) < 3:
        decisions.append("Focus growth on the top-performing segment highlighted above.")

    return {
        "findings": findings,
        "highlight": highlight,
        "decisions": decisions[:3],
        "opportunity": opportunity,
        "n_rows": n,
        "n_dims": len(cats),
    }


def _friendly_error(question: str, err: str) -> str:
    e = (err or "").lower()
    if "column" in e and ("not found" in e or "does not exist" in e or "binder" in e):
        reason = "I couldn't find that column in your data"
        etype = "column not found"
    elif "syntax" in e or "parser" in e:
        reason = "The query structure was unexpected"
        etype = "syntax"
    elif "no row" in e or "empty" in e:
        reason = "No data matched those filters"
        etype = "no rows"
    else:
        reason = "Unexpected technical issue"
        etype = "technical"

    simpler = "Show revenue by colour"
    try:
        prompt = (
            f'A data query failed.\nOriginal question: "{question}"\n'
            f"Error type: {etype}\nSimplified reason: {reason}\n\n"
            "Respond empathetically. Explain in plain English what went wrong. "
            "Suggest one simpler version of the question. Keep to 3 sentences maximum."
        )
        text = call_llm(prompt)
        if text:
            return text.strip()
    except Exception:
        pass
    return (
        f"Hmm, I had trouble with that one 🤔\n\n"
        f"I tried: {question}\n"
        f"Issue: {reason}\n\n"
        f"Want to try:\n→ '{simpler}'\n\n"
        "Or I can show you what data is available to query."
    )


def _oob_redirect(question: str, working_df: pd.DataFrame) -> str:
    qs = _suggested_qs(working_df, 2)
    q1 = qs[0] if qs else "Show revenue by colour"
    q2 = qs[1] if len(qs) > 1 else "Monthly revenue trend"
    try:
        prompt = (
            f'User asked something outside data scope:\n"{question}"\n\n'
            "Respond warmly. Acknowledge what they asked without dismissing them.\n"
            "Redirect to 2 specific data questions they COULD ask instead, pulled from:\n"
            f"- {q1}\n- {q2}\n"
            'Do not say "I cannot" — say "I\'m focused on" instead.\n'
            "Keep to 3-4 sentences maximum."
        )
        text = call_llm(prompt)
        if text:
            return text.strip()
    except Exception:
        pass
    return (
        "That's a lovely question — I'm set up for your sales and vehicle data, "
        "so I may not be the best dinner planner. Happy to help with insights "
        "from this dataset instead.\n\n"
        f"You could try:\n→ '{q1}'\n→ '{q2}'\n\n"
        "Ask anything about revenue, units, makes, regions, or trends — I'll dig in."
    )


def _blocked_reply(question: str) -> str:
    return (
        "🔒 Data Protection — I can only read and analyse your data. "
        "I'm not able to modify, delete or update any records.\n\n"
        "Your data is safe. If you need to make changes, contact your administrator"
        "source system directly."
    )


def _greeting_reply(working_df: pd.DataFrame) -> str:
    greet = _time_of_day_greeting()
    n = len(working_df) if working_df is not None else 0
    hook = ""
    insights = _safe_insights(working_df, limit=1)
    if insights:
        hook = (
            f"\nI noticed {insights[0].get('title', 'an interesting pattern')} "
            f"— want me to dig into that?"
        )
    turn = 0
    try:
        turn = int(get_state().get("turn_count") or 0)
    except Exception:
        turn = 0
    first = turn <= 1
    body = (
        f"{greet}\n\n"
        f"I can see you have {n:,} rows of automotive sales data loaded.\n\n"
        "Here are a few things I can help you explore today:\n"
        "• Revenue performance by colour or make\n"
        "• Top performing salespeople\n"
        "• Sales trends over time\n"
        "What would you like to start with?"
    )
    if first and hook:
        body = body + hook
    return body


def _clarification_prompt(question: str) -> str:
    return (
        "I want to make sure I give you the right answer! Are you asking about:\n"
        "A) Revenue performance\n"
        "B) Units sold\n"
        "C) Order count\n\n"
        "Just reply A, B or C"
    )


def _render_chat_chart(rdf: pd.DataFrame, question: str, key_prefix: str):
    """Chart controls in chat — mirrors Query tab Chart panel."""
    try:
        cols = list(rdf.columns)
        if len(cols) < 1:
            st.info("Chart not available")
            return
        nums = rdf.select_dtypes(include="number").columns.tolist()
        strs = rdf.select_dtypes(exclude="number").columns.tolist()
        ct = auto_chart_type(rdf, question or "")
        options = ["Bar", "Line", "Pie", "Scatter", "Area"]
        idx = options.index(ct) if ct in options else 0
        chart_type = st.selectbox(
            "Chart Type", options, index=idx, key=f"{key_prefix}_ctype",
        )
        x_default = strs[0] if strs else cols[0]
        y_default = nums[0] if nums else cols[-1]
        x = st.selectbox(
            "X", cols,
            index=cols.index(x_default) if x_default in cols else 0,
            key=f"{key_prefix}_x",
        )
        y = st.selectbox(
            "Y", cols,
            index=cols.index(y_default) if y_default in cols else len(cols) - 1,
            key=f"{key_prefix}_y",
        )
        build_chart(rdf, chart_type, x, y)
    except Exception:
        st.info("Chart not available for this result")


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

    hour = datetime.now().hour
    tod = "morning" if hour < 12 else ("afternoon" if hour < 17 else "evening")

    if is_greeting(question):
        return _greeting_reply(working_df if working_df is not None else pd.DataFrame())

    prompt = f"""You are an AI Data Concierge embedded in Capgemini's AI Data Platform.

Your personality:
  Professional but warm
  Confident but not arrogant
  Helpful and solution-oriented
  Brief and precise — no waffle

Your purpose:
  Help users explore their automotive sales dataset using natural language.

You can: answer data questions, explain results, run what-if scenarios,
surface patterns, guide users to better questions.
You cannot: modify/delete data, access external systems, answer outside this dataset.

Current dataset context:
{data_summary}

Semantic terms available:
{glossary_bits}

Conversation history:
{history}

Time of day: {tod}

User: "{question}"
This is not a data question.

Respond naturally and helpfully.
If related to your capabilities, explain.
If completely off-topic, gently redirect.
Keep to 2-3 sentences.
Always end with an invitation to ask about the data.
Assistant:"""
    text = call_llm(prompt)
    return (
        text or "Happy to help — ask me about revenue, colours, makes, or trends in your data."
    ).strip()


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
              const anchors = doc.querySelectorAll('#chat-scroll-anchor');
              if (anchors.length) {
                const a = anchors[anchors.length - 1];
                a.scrollIntoView({behavior: 'smooth', block: 'end'});
                let p = a.parentElement;
                for (let i = 0; i < 8 && p; i++) {
                  if (p.scrollHeight > p.clientHeight + 40) {
                    p.scrollTop = p.scrollHeight;
                    break;
                  }
                  p = p.parentElement;
                }
              }
            })();
            </script>
            """,
            height=0,
            width=0,
        )
    except Exception:
        pass


def _append_assistant(content, message_type, data=None):
    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": content,
        "message_type": message_type,
        "data": data or {},
        "timestamp": datetime.now().strftime("%H:%M"),
    })


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

    # 1. Destructive
    if detect_destructive(q):
        _append_assistant(_blocked_reply(q), "blocked")
        append_chat_exchange(q, result_summary=None, was_data_query=False)
        st.rerun()
        return

    # 2. Surprise me
    if detect_surprise_me(q):
        with st.spinner("✨ Digging for something interesting..."):
            result = run_surprise_analysis(working_df)
        _append_assistant(
            "✨ Here's something interesting I found in your data...",
            "surprise",
            {"surprise": result},
        )
        append_chat_exchange(q, result_summary=result.get("highlight"), was_data_query=True)
        st.rerun()
        return

    # 3. Clarification reply A/B/C
    if is_awaiting_clarification() and q.strip().lower() in (
        "a", "b", "c", "1", "2", "3", "a)", "b)", "c)",
    ):
        reconstructed = resolve_clarification(q.strip().lower()[0])
        if reconstructed:
            q = reconstructed
            # fall through to data query with reconstructed question
        else:
            _append_assistant(
                "I lost the clarification context — could you ask again?",
                "chat",
            )
            st.rerun()
            return
    else:
        # 4. OOB warm redirect
        if detect_oob(q):
            with st.spinner("💬 Thinking..."):
                reply = _oob_redirect(q, working_df)
            _append_assistant(reply, "oob")
            append_chat_exchange(q, result_summary=None, was_data_query=False)
            st.rerun()
            return

        # 5. Greeting
        if is_greeting(q):
            reply = _greeting_reply(working_df)
            _append_assistant(reply, "chat")
            append_chat_exchange(q, result_summary=None, was_data_query=False)
            st.rerun()
            return

        # 6. Ambiguous → clarification
        if detect_ambiguous(q):
            set_pending_clarification(q)
            _append_assistant(_clarification_prompt(q), "clarification")
            append_chat_exchange(q, result_summary=None, was_data_query=False)
            st.rerun()
            return

        # Conversational (non-data) — before data path
        if not is_data_question(q, working_df):
            with st.spinner("💬 Thinking..."):
                reply = _conversational_reply(q, working_df)
            append_chat_exchange(q, result_summary=None, was_data_query=False)
            _append_assistant(reply, "chat")
            st.rerun()
            return

        # What-if
        if whatif_engine is not None and whatif_engine.detect_whatif_query(q):
            with st.spinner("🔍 Running scenario..."):
                scenario = whatif_engine.parse_scenario(q, working_df)
                result = whatif_engine.run_scenario(working_df, scenario)
            append_chat_exchange(q, result_summary=result.get("narrative"), was_data_query=True)
            _append_assistant(
                result.get("narrative", "Scenario complete."),
                "whatif",
                {"whatif_result": result, "scenario": scenario},
            )
            st.rerun()
            return

    # 7. Data query
    with st.spinner("⚡ Querying your data with semantic layer..."):
        out = run_query(working_df, q)
        if isinstance(out, tuple) and len(out) == 4:
            df_result, sql, err, evidence = out
        else:
            df_result, sql, err = out[0], out[1], out[2]
            evidence = None

    if err:
        friendly = _friendly_error(q, str(err))
        _append_assistant(
            friendly, "error_friendly", {"sql": sql, "raw_error": str(err)},
        )
        st.rerun()
        return

    evidence = evidence or {}
    try:
        score, breakdown = compute_trust_score(evidence, df_result, working_df)
        evidence["trust_score"] = score
        evidence["trust_breakdown"] = breakdown
    except Exception:
        pass

    force = _should_force_narration(q)
    narr = _safe_narration(df_result, q, evidence)
    summary = (narr or {}).get("result_summary") or (
        f"{len(df_result)} rows returned" if isinstance(df_result, pd.DataFrame) else "Done"
    )
    append_chat_exchange(q, result_summary=summary, was_data_query=True)

    _append_assistant(
        (narr or {}).get("summary", "Here are the results."),
        "query",
        {
            "result_df": df_result,
            "sql": sql,
            "evidence": evidence,
            "narration": narr,
            "result_summary": summary,
            "force_narration": force or narration_on,
            "source_question": q,
            "glossary_matches": list(st.session_state.get("last_glossary_matches") or []),
        },
    )
    st.rerun()


def render_user_bubble(msg):
    st.markdown(
        f"""
        <div class="user-bubble chat-msg-gap">
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
    card_cls = {
        "chat": "assistant-card card-chat",
        "query": "assistant-card card-query",
        "whatif": "assistant-card card-whatif",
        "surprise": "assistant-card card-surprise",
        "blocked": "assistant-card card-blocked",
        "oob": "assistant-card card-oob",
        "clarification": "assistant-card card-clarification",
        "error_friendly": "assistant-card card-error",
        "error": "assistant-card card-error",
    }.get(mtype, "assistant-card card-chat")

    st.markdown(
        f"""
        <div class="assistant-bubble chat-msg-gap">
          <div class="assistant-avatar">🤖</div>
          <div class="{card_cls}">
        """,
        unsafe_allow_html=True,
    )

    if mtype in ("chat", "oob", "clarification", "blocked", "error", "error_friendly"):
        # Preserve newlines
        body = html.escape(str(msg.get("content", ""))).replace("\n", "<br>")
        st.markdown(f'<div class="chat-reply-text">{body}</div>', unsafe_allow_html=True)

    elif mtype == "surprise":
        sur = data.get("surprise") or {}
        st.markdown(
            f'<div class="surprise-header">{html.escape(str(msg.get("content","")))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="surprise-highlight">{html.escape(str(sur.get("highlight","")))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="surprise-rec-title">Based on everything analysed, '
            "here are 3 decisions I recommend today:</div>",
            unsafe_allow_html=True,
        )
        for i, d in enumerate(sur.get("decisions") or [], 1):
            st.markdown(
                f'<div class="finding-bullet">{i}. {html.escape(str(d))}</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div class="surprise-opp">Estimated revenue opportunity: '
            f'{html.escape(str(sur.get("opportunity","—")))}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Analysis based on {sur.get('n_rows', 0):,} data points "
            f"across {sur.get('n_dims', 0)} dimensions"
        )

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
            for m in matches[:3]:
                label = html.escape(str(m.get("term_name") or ""))
                expr = m.get("sql_expression") or m.get("source_column") or ""
                expr_s = html.escape(" ".join(str(expr).split())[:40])
                chips.append(
                    f"<span class='sem-term-badge'>{label}"
                    + (f"<span class='sem-expr'>= {expr_s}</span>" if expr_s else "")
                    + "</span>"
                )
            st.markdown(" ".join(chips), unsafe_allow_html=True)

        force = data.get("force_narration") or False
        show_narr = narration_on or force
        if show_narr:
            render_narration_card(data.get("narration"))

        render_trust_score_card(evidence)

        rdf = data.get("result_df")
        src_q = data.get("source_question") or msg.get("content") or ""
        if isinstance(rdf, pd.DataFrame):
            st.markdown(
                f'<div class="chat-results-label">📋 Query Results ({len(rdf):,} rows)</div>',
                unsafe_allow_html=True,
            )
            # Unique key from timestamp + question hash
            key_base = f"chat_{html.escape(str(msg.get('timestamp','')))}_{abs(hash(src_q)) % 10_000}"
            tab_t, tab_c = st.tabs(["📊 Table", "📈 Chart"])
            with tab_t:
                show_n = min(10, len(rdf))
                st.dataframe(rdf.head(show_n), use_container_width=True)
                if len(rdf) > 10:
                    with st.expander(f"Show all {len(rdf)} rows"):
                        st.dataframe(rdf, use_container_width=True)
            with tab_c:
                _render_chat_chart(rdf, src_q, key_base)

        sql = data.get("sql")
        if sql and not str(sql).startswith("--"):
            with st.expander("🔍 SQL used (click to inspect)"):
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

    chat_box = st.container(height=520, border=True)
    with chat_box:
        if not st.session_state.chat_messages:
            insights = _safe_insights(working_df, limit=4)
            st.markdown(
                """
                <div class="chat-welcome-card">
                  <div class="chat-welcome-title">👋 Hi! I've analysed your data.</div>
                  <div class="chat-welcome-subtitle">Ask about revenue, colours, makes — or say
                  <b>surprise me</b>. Follow-ups like "same for 2023" work too.</div>
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
        "Ask about your data, say hi, or try “surprise me”…",
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
