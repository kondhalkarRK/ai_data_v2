"""
ui/sidebar.py
"""

import inspect
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
        # BRAND  (logo above ASK - DB)
        # =========================
        st.markdown(
            """
            <div class="sidebar-brand">
              <div class="askdb-logo" aria-hidden="true">
                <svg viewBox="0 0 64 64" width="58" height="58">
                  <defs>
                    <linearGradient id="askdbG" x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stop-color="#38bdf8"/>
                      <stop offset="50%" stop-color="#6366f1"/>
                      <stop offset="100%" stop-color="#34d399"/>
                    </linearGradient>
                  </defs>
                  <ellipse cx="32" cy="24" rx="15" ry="5.5" fill="none" stroke="url(#askdbG)" stroke-width="2.2"/>
                  <path d="M17 24 v14 c0 3.2 6.7 5.8 15 5.8s15-2.6 15-5.8 V24" fill="none" stroke="url(#askdbG)" stroke-width="2.2"/>
                  <ellipse cx="32" cy="31" rx="15" ry="5.5" fill="none" stroke="url(#askdbG)" stroke-width="1.35" opacity=".55"/>
                  <circle cx="13" cy="14" r="3.1" fill="#38bdf8"/>
                  <circle cx="22" cy="8" r="2.2" fill="#818cf8"/>
                  <circle cx="51" cy="15" r="2.6" fill="#a78bfa"/>
                  <circle cx="48" cy="50" r="2.8" fill="#34d399"/>
                  <path d="M13 14 L22 20 M22 8 L28 18 M51 15 L41 22 M48 50 L40 40" stroke="#818cf8" stroke-width="1.25" fill="none" opacity=".85"/>
                  <rect x="25.5" y="43" width="3.4" height="9" rx="1" fill="#38bdf8"/>
                  <rect x="30.5" y="38" width="3.4" height="14" rx="1" fill="#818cf8"/>
                  <rect x="35.5" y="41" width="3.4" height="11" rx="1" fill="#34d399"/>
                </svg>
              </div>
              <div class="sidebar-hero-title">ASK - DB</div>
              <div class="sidebar-hero-sub">Ask your database in plain English</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        th_l, th_r = st.columns([0.38, 0.62], gap="small")
        with th_l:
            with st.popover("ℹ️", help="How to ask questions"):
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
        with th_r:
            _theme_labels = {"light": "☀️ Light", "dark": "🌙 Dark", "ai": "✨ AI"}
            st.selectbox(
                "Appearance",
                options=list(_theme_labels.keys()),
                format_func=lambda k: _theme_labels[k],
                label_visibility="collapsed",
                key="ui_theme",
                help="Switch Light / Dark / AI appearance",
            )

        section_spacer()

        # =========================
        # FILES
        # =========================
        with st.container(border=True):
            st.markdown('<div class="sb-upload-wrap">', unsafe_allow_html=True)
            section_title("📁 UPLOAD FILES HERE")
            section_spacer()

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

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # JOIN (settings pop-out)
        # =========================
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

        st.markdown('<div class="sb-join-card">', unsafe_allow_html=True)
        j1, j2 = st.columns([4.6, 1.1])
        with j1:
            st.markdown(
                f'<div class="sb-join-row">'
                f'<span class="sb-join-kicker">Join</span>'
                f'<span class="sb-join-status sb-join-status-{join_kind}">{join_status}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with j2:
            if st.button(
                "⚙️",
                key="sidebar_join_settings",
                help="Open join settings",
            ):
                join_settings_dialog()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="sb-semantic-wrap">', unsafe_allow_html=True)
            section_title("🧬 SEMANTIC LAYER")
            section_spacer()

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
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # USAGE
        # =========================
        with st.container(border=True):
            st.markdown('<div class="sb-llm-wrap">', unsafe_allow_html=True)
            section_title("⚡ LLM USAGE STATUS")
            section_spacer()

            calls  = st.session_state.get("llm_calls", 0)
            tokens = st.session_state.get("total_tokens", 0)

            max_calls = max(
                st.session_state.get("max_llm_calls", 1), 1
            )

            status_row("Calls",  calls,          "#a5b4fc")
            status_row("Tokens", f"{tokens:,}",  "#a5b4fc")

            section_spacer()
            st.progress(min(calls / max_calls, 1.0))
            section_spacer()

            if st.button("RESET", use_container_width=True, key="sidebar_reset"):
                st.session_state.llm_calls    = 0
                st.session_state.total_tokens = 0
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # COLLAPSED NAV  (below LLM — click to open)
        # =========================
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
