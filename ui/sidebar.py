"""
ui/sidebar.py
"""

import base64
import inspect
from pathlib import Path

import pandas as pd
import streamlit as st

from core.data_backend.factory import get_backend, postgres_mode_enabled
from core.utils import load_files
from features.question_cache import cache_store

try:
    from semantic.semantic_loader import get_semantic_loader
    _SEMANTIC_AVAILABLE = True
except ImportError:
    _SEMANTIC_AVAILABLE = False

try:
    from semantic.industry_packs import list_packs, get_active_pack_id, activate_pack
    _PACKS_AVAILABLE = True
except ImportError:
    _PACKS_AVAILABLE = False

try:
    from config.constants import OKF_ENABLED
except ImportError:
    OKF_ENABLED = False

try:
    from features.okf_knowledge.okf_bootstrap import bootstrap_business_knowledge
    from features.okf_knowledge.okf_store import list_bundles
    from features.okf_knowledge.okf_retriever import indexed_concept_count

    _OKF_AVAILABLE = OKF_ENABLED
except ImportError:
    _OKF_AVAILABLE = False


_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "ask_db_logo.png"
_LOGO_B64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")


# ==========================================================
# Upload Dialog
# ==========================================================

@st.dialog("Upload CSV Files")
def upload_dialog():

    uploaded_files = st.file_uploader(
        "Select CSV Files",
        accept_multiple_files=True,
        type=["csv"],
        key="dialog_upload",
    )

    if uploaded_files:

        st.info(f"{len(uploaded_files)} file(s) selected")

        if st.button("UPLOAD", use_container_width=True):

            # CHANGED: wrapped load_files in st.spinner so user
            # sees a clear loading indicator while files are processed
            with st.spinner("Loading files, please wait..."):
                try:
                    load_files(uploaded_files)
                    try:
                        from core.conversation_state import clear_sql_anchor
                        clear_sql_anchor()
                    except Exception:
                        pass

                    st.success(f"Loaded {len(uploaded_files)} file(s)")
                    st.rerun()

                except Exception as e:
                    st.error(str(e))


# ==========================================================
# Join settings dialog
# ==========================================================

_join_dialog_kwargs = {}
try:
    if "width" in inspect.signature(st.dialog).parameters:
        _join_dialog_kwargs["width"] = "large"
except (TypeError, ValueError):
    _join_dialog_kwargs = {}


@st.dialog("Join settings", **_join_dialog_kwargs)
def join_settings_dialog():
    from core.join_engine import get_working_df
    from core.data_backend.factory import postgres_mode_enabled
    from core.semantic_joins import load_semantic_joins
    from ui.tab_join import render as render_join

    if postgres_mode_enabled():
        payload = load_semantic_joins()
        st.markdown("### Semantic join map")
        st.caption("Source: active `semantic/semantic_model.yaml` (insurance PostgreSQL pack).")
        if not payload.get("ok"):
            st.error(payload.get("error") or "Could not load semantic joins.")
        else:
            st.caption(
                f"{payload['count']} relationships · "
                f"{len(payload.get('facts') or [])} facts · "
                f"{len(payload.get('dims') or [])} dimensions"
            )
            if payload.get("coverage"):
                st.markdown("#### Dimension coverage")
                st.dataframe(
                    pd.DataFrame(payload["coverage"]),
                    use_container_width=True,
                    hide_index=True,
                )
            if payload.get("rows"):
                st.markdown("#### Join details")
                st.dataframe(
                    pd.DataFrame(payload["rows"]),
                    use_container_width=True,
                    hide_index=True,
                )
                st.caption(
                    "`dim_agent` joins `fact_policy_monthly` directly and reaches "
                    "`fact_claims` through `dim_policy` (policy_id → agent_id)."
                )
            else:
                st.warning("No relationships found in semantic_model.yaml.")
        if st.button("Close", key="join_dialog_close_pg", use_container_width=True):
            st.rerun()
        return

    dfs = st.session_state.get("dfs") or {}
    if not dfs:
        st.info("Upload CSV files first, then configure joins here.")
        if st.button("Close", key="join_dialog_close_empty", use_container_width=True):
            st.rerun()
        return

    tables = list(dfs.keys())
    working_df = get_working_df()
    render_join(working_df, tables, dfs)
    st.divider()
    if st.button("Close", key="join_dialog_close", use_container_width=True):
        st.rerun()


@st.dialog("LLM settings", **_join_dialog_kwargs)
def llm_settings_dialog():
    from config.llm_catalog import (
        CG_ENDPOINTS,
        DEFAULT_FAMILY,
        DEFAULT_TEMPERATURE,
        DEFAULT_TIER,
        get_profile,
        models_for_family,
        questions_per_dollar,
        tokens_per_dollar,
    )

    family = st.session_state.get("llm_family") or DEFAULT_FAMILY
    tier = st.session_state.get("llm_tier") or DEFAULT_TIER
    temperature = float(st.session_state.get("llm_temperature") or DEFAULT_TEMPERATURE)
    current_model = st.session_state.get("llm_model_id")

    st.caption(
        "Capgemini Studio routes only. Pick GPT or Claude, then the exact endpoint."
    )
    family = st.radio(
        "Provider",
        ["gpt", "claude"],
        index=0 if family == "gpt" else 1,
        format_func=lambda v: "OpenAI (openai.*)" if v == "gpt" else "Bedrock Claude (anthropic.*)",
        horizontal=True,
        key="llm_settings_family",
    )
    family_models = models_for_family(family)
    ids = [item["id"] for item in family_models]
    default_profile = get_profile(family, tier)
    if current_model not in ids:
        current_model = default_profile["model"]
    chosen_id = st.selectbox(
        "Capgemini endpoint",
        ids,
        index=ids.index(current_model) if current_model in ids else 0,
        format_func=lambda mid: next(
            f"{m['label']} · {m['id']}" for m in family_models if m["id"] == mid
        ),
        key="llm_settings_model_id",
    )
    profile = get_profile(family, tier, chosen_id)
    per_dollar = tokens_per_dollar(profile["usd_per_1m"])
    q_plain = questions_per_dollar(profile["usd_per_1m"], with_narration=False)
    q_narr = questions_per_dollar(profile["usd_per_1m"], with_narration=True)
    st.markdown(f"**{profile['label']}**")
    st.caption(f"Request model id: `{profile['model']}`")
    st.caption(
        f"Indicative price: ${profile['usd_per_1m']:.2f} per 1M tokens · "
        f"$1 ≈ {per_dollar:,} tokens"
    )
    st.caption(
        f"~$1 buys ≈ **{q_plain:,}** questions without narration · "
        f"**{q_narr:,}** with narration "
        "(indicative; ~2.5k / ~6k tokens per turn)."
    )

    with st.expander("Studio catalog", expanded=False):
        rows = []
        for item in CG_ENDPOINTS:
            rows.append(
                {
                    "Provider": "OpenAI" if item["family"] == "gpt" else "Bedrock",
                    "Size": item["tier"].title(),
                    "Label": item["label"],
                    "Model id": item["id"],
                    "$ / 1M tokens": f"${item['usd_per_1m']:.2f}",
                    "$1 buys tokens": f"{tokens_per_dollar(item['usd_per_1m']):,}",
                    "Q/$ no narr.": f"{questions_per_dollar(item['usd_per_1m'], with_narration=False):,}",
                    "Q/$ + narr.": f"{questions_per_dollar(item['usd_per_1m'], with_narration=True):,}",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            "Question estimates assume ~2,500 tokens/turn without narration and "
            "~6,000 with narration (SQL + insight). Actual usage varies."
        )

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.2,
        value=min(max(temperature, 0.0), 1.2),
        step=0.1,
        help="Lower is more factual SQL/KPI wording. Higher is more varied narration.",
        key="llm_settings_temperature",
    )
    st.caption("0.0–0.2 recommended for SQL. 0.4–0.7 can improve narrative tone.")

    if st.button("Apply", type="primary", use_container_width=True, key="llm_settings_apply"):
        st.session_state.llm_family = family
        st.session_state.llm_tier = profile["tier"]
        st.session_state.llm_model_id = profile["model"]
        st.session_state.llm_temperature = float(temperature)
        st.session_state._llm_profile_chosen = True
        st.toast(f"Using {profile['model']} · temp {temperature:.1f}", icon="⚡")
        st.rerun()
    if st.button("Close", key="llm_settings_close", use_container_width=True):
        st.rerun()

def section_title(title):
    st.markdown(
        f"""
        <div class="sb-title">
            {title}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_row(label, value, color="#38bdf8"):
    st.markdown(
        f"""
        <div class="sb-row">
            <span class="sb-label">{label}</span>
            <span class="sb-value" style="color:{color}">
                {value}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# CHANGED: added a small vertical spacer helper to reduce
# tightness between sidebar sections
def section_spacer():
    st.markdown(
        "<div style='margin-top:8px;margin-bottom:2px;'></div>",
        unsafe_allow_html=True,
    )


# ==========================================================
# Sidebar
# ==========================================================

def render():

    with st.sidebar:

        # =========================
        # BRAND
        # =========================
        st.markdown(
            f"""
            <div class="sidebar-brand-logo" style="margin:0 0 10px 0;padding:0 2px;display:flex;justify-content:center;width:100%;">
              <img src="data:image/png;base64,{_LOGO_B64}" alt="ASK-DB"
                style="display:block;width:148px;max-width:100%;height:auto;" />
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sb-util-row">', unsafe_allow_html=True)
        _sp1, _note_col, _theme_col, _sp2 = st.columns([1.15, 0.85, 0.85, 1.15], gap="small")
        with _note_col:
            with st.popover("📝", help="Notes — how to ask"):
                st.markdown("#### Ask better questions")
                st.markdown(
                    """
**Good questions (clear metric + slice + time):**
- Show total **units sold by make** for **2025**
- **Monthly revenue trend** by region in **2024**
- **Top 10** salespeople by **revenue** in **Q3 2025**
- Compare **EV unit share by year** between **2020 and 2025**

**Follow-ups & drill-downs (uses prior context):**
- *Same but for 2024* · *What about Ford?* · *Drill down by region*
- *Break that down by month* · *Now show by colour*

**Avoid (wastes LLM calls):**
- Vague: *“show sales”*, *“performance”*, *“tell me about EV”*
- Off-topic: recipes, weather, jokes unrelated to your data

**Tip:** Chat Room remembers your last query — use follow-up phrases instead of re-asking from scratch.
                    """
                )
        with _theme_col:
            with st.popover("🎨", help="Appearance"):
                st.caption("Theme")
                t1, t2, t3 = st.columns(3)
                with t1:
                    if st.button("☀️", key="theme_pick_light", help="Light", use_container_width=True):
                        st.session_state.ui_theme = "light"
                        st.rerun()
                with t2:
                    if st.button("🌙", key="theme_pick_dark", help="Dark", use_container_width=True):
                        st.session_state.ui_theme = "dark"
                        st.rerun()
                with t3:
                    if st.button("✨", key="theme_pick_ai", help="AI", use_container_width=True):
                        st.session_state.ui_theme = "ai"
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        section_spacer()

        # =========================
        # COLLAPSED NAV — click to open
        # =========================
        _postgres_mode = postgres_mode_enabled()
        _pg_backend = get_backend() if _postgres_mode else None
        _pg_healthy = False
        _pg_message = ""
        _pg_counts: dict = {}
        if _pg_backend is not None:
            _pg_healthy, _pg_message = _pg_backend.health_check()
            if _pg_healthy:
                _pg_counts = _pg_backend.table_row_counts()

        if _postgres_mode:
            with st.expander("🗄️ PostgreSQL", expanded=True):
                status_row(
                    "Status",
                    "CONNECTED" if _pg_healthy else "OFFLINE",
                    "#6ee7b7" if _pg_healthy else "#fca5a5",
                )
                fact_claims = int(_pg_counts.get("fact_claims") or 0)
                total_loaded = int(sum(_pg_counts.values())) if _pg_counts else 0
                status_row("Tables", len(_pg_backend.list_base_tables()) if _pg_healthy else 0)
                status_row("Claims loaded", f"{fact_claims:,}", "#6ee7b7")
                status_row("Physical table rows", f"{total_loaded:,}", "#a5b4fc")
                st.caption(_pg_message)
                st.caption("Views such as v_claims_enriched are joins, not extra loaded records.")
                if _pg_counts:
                    with st.expander("Row counts by table", expanded=False):
                        for name, n in sorted(_pg_counts.items()):
                            status_row(name, f"{n:,}")
        else:
            with st.expander("📁 Upload files", expanded=False):
                st.markdown('<div class="sb-upload-wrap">', unsafe_allow_html=True)
                file_count = len(st.session_state.get("dfs", {}))
                c1, c2 = st.columns([3, 1])
                with c1:
                    status_row("Files Loaded", file_count, "#fcd34d")
                with c2:
                    if st.button(
                        "＋",
                        use_container_width=True,
                        help="Add Files",
                        key="sidebar_upload_plus",
                    ):
                        upload_dialog()
                st.markdown("</div>", unsafe_allow_html=True)

        dfs_loaded = st.session_state.get("dfs") or {}
        semantic_used = st.session_state.get("semantic_join_used", None)
        if len(dfs_loaded) <= 1:
            join_kind, join_status = "idle", "Not needed"
        elif semantic_used is True:
            join_kind, join_status = "active", "Active"
        elif semantic_used is False:
            join_kind, join_status = "fallback", "Fallback"
        else:
            join_kind, join_status = "pending", "Pending"

        with st.expander("🔗 Join", expanded=False):
            if _postgres_mode:
                from core.semantic_joins import load_semantic_joins

                payload = load_semantic_joins()
                join_count = int(payload.get("count") or 0)
                status_row("Mode", "Semantic model", "#6ee7b7")
                status_row("Joins", join_count, "#a5b4fc")
                if st.button("⚙️ Settings", key="sidebar_join_settings_pg", use_container_width=True):
                    join_settings_dialog()
            else:
                _join_col_kwargs = {"gap": "small"}
                try:
                    if "vertical_alignment" in inspect.signature(st.columns).parameters:
                        _join_col_kwargs["vertical_alignment"] = "center"
                except (TypeError, ValueError):
                    pass
                j_left, j_right = st.columns([1.05, 1.35], **_join_col_kwargs)
                with j_left:
                    st.markdown(
                        f'<div class="sb-join-row">'
                        f'<span class="sb-join-kicker sb-join-status-{join_kind}">{join_status}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with j_right:
                    if st.button("⚙️ Settings", key="sidebar_join_settings"):
                        join_settings_dialog()

        with st.expander("🧬 Semantic layer", expanded=False):
            semantic_used = st.session_state.get("semantic_join_used", None)
            if _postgres_mode:
                join_status = "DATABASE"
                join_color = "#6ee7b7"
            elif semantic_used is True:
                join_status = "ACTIVE"
                join_color  = "#6ee7b7"
            elif semantic_used is False:
                join_status = "FALLBACK"
                join_color  = "#fcd34d"
            else:
                join_status = "PENDING"
                join_color  = "#fca5a5"

            model_status = "UNAVAILABLE"
            model_color  = "#fca5a5"
            if _SEMANTIC_AVAILABLE:
                try:
                    get_semantic_loader()
                    model_status = "LOADED"
                    model_color  = "#6ee7b7"
                except Exception:
                    model_status = "ERROR"
                    model_color  = "#fca5a5"
            status_row("Join",  join_status,  join_color)
            status_row("Model", model_status, model_color)

        with st.expander("⚡ LLM usage", expanded=False):
            from config.llm_catalog import tokens_per_dollar, estimate_usd
            from config.settings import get_llm_config
            from core.llm_client import usage_caption

            cfg = get_llm_config()
            calls = int(st.session_state.get("llm_calls", 0) or 0)
            tokens = int(st.session_state.get("total_tokens", 0) or 0)
            max_calls = max(int(st.session_state.get("max_llm_calls", 60) or 60), 1)
            max_tokens = max(int(st.session_state.get("max_llm_tokens", 30_000) or 30_000), 1)
            usd_per_1m = float(cfg.get("usd_per_1m") or 0)
            est = float(st.session_state.get("llm_est_usd") or estimate_usd(tokens, usd_per_1m))
            status_row("Model", cfg.get("label") or "GPT · High", "#a5b4fc")
            status_row("Calls", f"{calls}/{max_calls}", "#a5b4fc")
            tok_disp = f"{tokens:,}/{max_tokens // 1000}K" if max_tokens >= 1000 else f"{tokens:,}/{max_tokens}"
            status_row("Tokens", tok_disp, "#a5b4fc")
            status_row("Est. cost", f"${est:.4f}", "#6ee7b7")
            st.caption(usage_caption())
            st.caption(
                f"$1 ≈ {tokens_per_dollar(usd_per_1m):,} tokens · "
                f"temp {float(cfg.get('temperature') or 0):.1f}"
            )
            st.caption("Call budget")
            st.progress(min(calls / max_calls, 1.0))
            st.caption("Token budget")
            st.progress(min(tokens / max_tokens, 1.0))
            log = list(st.session_state.get("llm_usage_log") or [])
            if log:
                st.caption("Recent calls")
                for item in log[-5:][::-1]:
                    purpose = item.get("purpose") or "other"
                    tot = int(item.get("total_tokens_est") or 0)
                    st.caption(f"• {purpose} · {tot:,} tok")
            if st.button("⚙️ Settings", use_container_width=True, key="sidebar_llm_settings"):
                llm_settings_dialog()
            if st.button("RESET", use_container_width=True, key="sidebar_reset"):
                st.session_state.llm_calls = 0
                st.session_state.total_tokens = 0
                st.session_state.llm_est_usd = 0.0
                st.session_state.llm_usage_log = []
                st.rerun()

        with st.expander("💾 Saved questions", expanded=False):
            saved_count = cache_store.count_active()
            status_row("Saved", saved_count, "#a5b4fc")
            recent = cache_store.list_recent(limit=6)
            if recent:
                for item in recent:
                    q_text = (item.get("question") or "")[:72]
                    if len(item.get("question") or "") > 72:
                        q_text += "…"
                    tag = "⚡ instant" if item.get("has_result") else "SQL only"
                    st.caption(f"• {q_text} ({tag})")
            else:
                st.caption("Ask a question once — repeats skip the LLM.")
            if st.button("CLEAR", use_container_width=True, key="sidebar_clear_saved"):
                removed = cache_store.clear_all()
                st.success(f"Cleared {removed} saved question(s)")
                st.rerun()

        if _PACKS_AVAILABLE:
            with st.expander("🌐 Industry pack", expanded=False):
                packs = list_packs()
                if not packs:
                    st.caption("No packs found in semantic/packs/")
                else:
                    pack_ids    = [p["id"]    for p in packs]
                    pack_labels = [f"{p['icon']} {p['label']}" for p in packs]
                    active_id   = get_active_pack_id()
                    default_idx = (
                        pack_ids.index(active_id)
                        if active_id in pack_ids else 0
                    )
                    chosen_label = st.selectbox(
                        "Domain",
                        pack_labels,
                        index=default_idx,
                        label_visibility="collapsed",
                        key="industry_pack_select",
                    )
                    chosen_id = pack_ids[pack_labels.index(chosen_label)]
                    status_row(
                        "Active",
                        next(p["label"] for p in packs if p["id"] == active_id),
                        "#a78bfa"
                    )
                    if chosen_id != active_id:
                        if st.button(
                            f"SWITCH TO {chosen_id.upper()}",
                            use_container_width=True
                        ):
                            ok, msg = activate_pack(chosen_id)
                            if ok:
                                st.session_state.pop("_okf_autosseed_done", None)
                                st.success(msg)
                            else:
                                st.error(msg)
                            st.rerun()

        if _OKF_AVAILABLE:
            with st.expander("📚 Knowledge base", expanded=False):
                bundles = list_bundles()
                doc_count = len(bundles)
                concept_count = indexed_concept_count()
                c1, c2 = st.columns(2)
                with c1:
                    status_row("Docs", doc_count, "#38bdf8")
                with c2:
                    status_row("Concepts", concept_count, "#38bdf8")
                st.caption(
                    "Business documents (handbooks, targets, strategy, SOPs) in "
                    "doc/business_knowledge/ — separate from business_glossary.yaml."
                )
                if st.button(
                    "INDEX ACTIVE PACK",
                    use_container_width=True,
                    key="sidebar_index_active_knowledge",
                ):
                    with st.spinner("Extracting and indexing business documents..."):
                        summary = bootstrap_business_knowledge(force=True)
                    st.success(
                        f"Indexed {summary.get('indexed', 0)} concepts from "
                        f"{summary.get('docs', 0)} documents."
                    )
                    st.rerun()
        else:
            with st.expander("📚 Knowledge base", expanded=False):
                st.caption("OKF modules unavailable — check features/okf_knowledge.")
