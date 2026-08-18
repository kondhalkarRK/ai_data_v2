"""
ui/sidebar.py
"""

import inspect
from pathlib import Path
import streamlit as st

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

# OKF imports disabled — wire back when OKF_ENABLED = True
_OKF_AVAILABLE = False
# try:
#     from features.okf_knowledge.pdf_extractor import extract_pdf_to_concepts, pdf_extraction_available
#     from features.okf_knowledge.okf_store import write_bundle, list_bundles, clear_all_bundles
#     from features.okf_knowledge.okf_retriever import reindex_all, indexed_concept_count, clear_index
#     _OKF_AVAILABLE = OKF_ENABLED
# except ImportError:
#     _OKF_AVAILABLE = False


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
    from ui.tab_join import render as render_join

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
        # BRAND  (provided logo + tagline + icon utilities)
        # =========================
        logo_path = Path(__file__).resolve().parents[1] / "assets" / "ask_db_logo.png"
        st.markdown('<div class="sidebar-brand">', unsafe_allow_html=True)
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
        st.markdown(
            '<div class="sidebar-tagline">Ask. Explore. Discover</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

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
            st.markdown(
                f'<div class="sb-join-row">'
                f'<span class="sb-join-kicker">Status</span>'
                f'<span class="sb-join-status sb-join-status-{join_kind}">{join_status}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("⚙️ Join settings", key="sidebar_join_settings", use_container_width=True):
                join_settings_dialog()

        with st.expander("🧬 Semantic layer", expanded=False):
            semantic_used = st.session_state.get("semantic_join_used", None)
            if semantic_used is True:
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
            calls  = st.session_state.get("llm_calls", 0)
            tokens = st.session_state.get("total_tokens", 0)
            max_calls = max(st.session_state.get("max_llm_calls", 1), 1)
            status_row("Calls",  calls,          "#a5b4fc")
            status_row("Tokens", f"{tokens:,}",  "#a5b4fc")
            st.progress(min(calls / max_calls, 1.0))
            if st.button("RESET", use_container_width=True, key="sidebar_reset"):
                st.session_state.llm_calls    = 0
                st.session_state.total_tokens = 0
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

        with st.expander("💬 Conversation", expanded=False):
            try:
                from core.conversation_state import get_state, clear_state
                conv = get_state()
            except Exception:
                conv = st.session_state.get("conversation_state") or {}

                def clear_state():
                    st.session_state.conversation_state = {
                        "active_intent": None,
                        "last_resolved": {},
                        "prior_metric": None,
                        "prior_dimensions": [],
                        "prior_filters": {},
                        "prior_time_grain": None,
                        "turn_count": 0,
                        "last_question": None,
                        "is_followup": False,
                        "inherited_context": {},
                    }

            if conv.get("turn_count", 0) > 0:
                st.markdown(
                    f"""
                    <div class='conv-state-panel'>
                      <div class='query-stat-row'>
                        <span style='color:#94a3b8;'>Active Metric</span>
                        <span style='color:#a5b4fc;font-weight:600;'>
                          {conv.get('prior_metric') or '—'}
                        </span>
                      </div>
                      <div class='query-stat-row'>
                        <span style='color:#94a3b8;'>Turn Count</span>
                        <span style='color:#6ee7b7;font-weight:600;'>
                          {conv.get('turn_count', 0)}
                        </span>
                      </div>
                      <div class='query-stat-row'>
                        <span style='color:#94a3b8;'>Last Intent</span>
                        <span style='color:#fcd34d;font-weight:600;'>
                          {conv.get('active_intent') or '—'}
                        </span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    "🔄 Clear Conversation",
                    use_container_width=True,
                    key="sidebar_clear_conv",
                ):
                    clear_state()
                    st.session_state.chat_messages = []
                    st.toast("Conversation cleared", icon="🔄")
                    st.rerun()
            else:
                st.caption("No active conversation. Ask a question to start.")

        with st.expander("📊 Session stats", expanded=False):
            stats = st.session_state.get(
                "query_stats",
                {"deterministic": 0, "fallback": 0, "cache": 0},
            )
            evidence_list = st.session_state.get("execution_evidence") or []
            if evidence_list:
                counts = {"deterministic": 0, "fallback": 0, "cache": 0}
                for ev in evidence_list:
                    p = (ev or {}).get("execution_path")
                    if p in counts:
                        counts[p] += 1
                stats = counts

            total = sum(int(stats.get(k, 0) or 0) for k in ("deterministic", "fallback", "cache"))
            if total > 0:
                st.markdown(
                    f"""
                    <div class='conv-state-panel'>
                      <div class='query-stat-row'>
                        <span>✅ Deterministic</span>
                        <span style='color:#6ee7b7;font-weight:700;'>{stats.get('deterministic',0)}</span>
                      </div>
                      <div class='query-stat-row'>
                        <span>⚠️ AI Generated</span>
                        <span style='color:#fcd34d;font-weight:700;'>{stats.get('fallback',0)}</span>
                      </div>
                      <div class='query-stat-row'>
                        <span>🔒 Cached</span>
                        <span style='color:#93c5fd;font-weight:700;'>{stats.get('cache',0)}</span>
                      </div>
                      <div class='query-stat-row' style='border:none;padding-top:6px;'>
                        <span style='color:#64748b;'>Total queries</span>
                        <span style='font-weight:700;'>{total}</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                det_pct = round(stats.get("deterministic", 0) / total * 100) if total else 0
                st.markdown(f"**Determinism Rate: {det_pct}%**")
                st.progress(det_pct / 100)
            else:
                st.caption("No queries yet this session.")

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
                                st.success(msg)
                            else:
                                st.error(msg)
                            st.rerun()

        if False and _OKF_AVAILABLE:
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
        else:
            with st.expander("📚 Knowledge base", expanded=False):
                st.caption("OKF modules unavailable — check features/okf_knowledge.")
