"""
ui/sidebar.py
"""

import streamlit as st

from core.utils import load_files
from features.materialized_views import view_store

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
    from features.okf_knowledge.pdf_extractor import extract_pdf_to_concepts, pdf_extraction_available
    from features.okf_knowledge.okf_store import write_bundle, list_bundles, clear_all_bundles
    from features.okf_knowledge.okf_retriever import reindex_all, indexed_concept_count
    _OKF_AVAILABLE = True
except ImportError:
    _OKF_AVAILABLE = False


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

                    st.session_state.sidebar_uploaded_names = [
                        getattr(f, "name", "uploaded_file")
                        for f in uploaded_files
                    ]

                    st.success(f"Loaded {len(uploaded_files)} file(s)")
                    st.rerun()

                except Exception as e:
                    st.error(str(e))


# ==========================================================
# Helpers
# ==========================================================

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
        # HERO HEADER
        # =========================
        st.markdown(
            """
            <div class="sidebar-hero">
                <div class="sidebar-hero-icon">🧠</div>
                <div class="sidebar-hero-text">
                    <div class="sidebar-hero-title">AI Command Center</div>
                    <div class="sidebar-hero-sub">Workspace status &amp; controls</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # CHANGED: spacer after hero for breathing room
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
        # SEMANTIC
        # =========================
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

            c1, c2 = st.columns(2)

            with c1:
                if st.button("RESET", use_container_width=True, key="sidebar_reset"):
                    st.session_state.llm_calls    = 0
                    st.session_state.total_tokens = 0
                    st.rerun()

            with c2:
                if st.button("CACHE", use_container_width=True, key="sidebar_cache"):
                    st.session_state.memory      = {}
                    st.session_state.last_plan   = None
                    st.session_state.last_query  = ""
                    st.session_state.query_history = []
                    try:
                        from core.conversation_state import clear_sql_anchor
                        clear_sql_anchor()
                    except Exception:
                        pass
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # MATERIALIZED VIEWS
        # =========================
        with st.container(border=True):
            st.markdown('<div class="sb-views-wrap">', unsafe_allow_html=True)
            section_title("🗂️ VIEWS")
            section_spacer()

            active_views = view_store.count_active_views()

            status_row("Active", active_views, "#a5b4fc")

            section_spacer()

            if st.button("CLEAR", use_container_width=True, key="sidebar_clear_views"):
                removed = view_store.clear_all_views()
                st.success(f"Cleared {removed} view(s)")
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # CONVERSATION STATE (Prompt 2)
        # =========================
        with st.container(border=True):
            st.markdown('<div class="sb-conv-wrap">', unsafe_allow_html=True)
            section_title("💬 CONVERSATION")
            section_spacer()

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

            with st.expander("💬 Conversation", expanded=False):
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

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # QUERY PATH STATS (Prompt 2)
        # =========================
        with st.container(border=True):

            section_title("📊 SESSION STATS")
            section_spacer()

            with st.expander("📊 Session Stats", expanded=False):
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

        section_spacer()

        # =========================
        # DOMAIN SCOPE HINT (Prompt 2)
        # =========================
        with st.container(border=True):

            section_title("🎯 DOMAIN SCOPE")
            section_spacer()

            with st.expander("💡 What can I ask?", expanded=False):
                try:
                    from core.metric_registry import get_metric_registry
                    registry = get_metric_registry()
                    metrics = registry.list_measures() or registry.list_metrics()
                    st.markdown("**Available Metrics:**")
                    for m in metrics[:8]:
                        st.markdown(f"• {m.replace('_', ' ').title()}")
                    st.markdown("---")
                    st.markdown("**Example Questions:**")
                    st.markdown("• *Show revenue by colour for 2023*")
                    st.markdown("• *Top 10 salespeople by units sold*")
                    st.markdown("• *What if revenue increased by 20%?*")
                    st.markdown("• *Find anomalies in my data*")
                    st.markdown("• *Why is silver performing low?*")
                except Exception:
                    st.caption("Ask questions about your uploaded data.")

        # CHANGED: spacer between sections
        section_spacer()

        # =========================
        # INDUSTRY PACK (NEW)
        # =========================
        if _PACKS_AVAILABLE:

            with st.container(border=True):

                section_title("🌐 INDUSTRY PACK")

                # CHANGED: spacer below title
                section_spacer()

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

                    # CHANGED: spacer before switch button
                    section_spacer()

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

        # CHANGED: spacer between sections
        section_spacer()

        # # =========================
        # # KNOWLEDGE BASE — OKF (NEW)
        # # =========================
        # if _OKF_AVAILABLE:

        #     with st.container(border=True):

        #         section_title("📚 KNOWLEDGE BASE (OKF)")

        #         # CHANGED: spacer below title
        #         section_spacer()

        #         bundles       = list_bundles()
        #         doc_count     = len(bundles)
        #         concept_count = indexed_concept_count()

        #         c1, c2 = st.columns(2)
        #         with c1:
        #             status_row("Docs",     doc_count,     "#38bdf8")
        #         with c2:
        #             status_row("Concepts", concept_count, "#38bdf8")

        #         # CHANGED: spacer before uploader
        #         section_spacer()

        #         if not pdf_extraction_available():
        #             st.caption("Install pypdf to enable PDF ingestion.")
        #         else:
        #             uploaded_pdf = st.file_uploader(
        #                 "Add a business PDF",
        #                 type=["pdf"],
        #                 label_visibility="collapsed",
        #                 key="okf_pdf_upload",
        #             )

        #             if uploaded_pdf is not None:
        #                 if st.button(
        #                     "INGEST INTO KNOWLEDGE BASE",
        #                     use_container_width=True
        #                 ):
        #                     # CHANGED: replaced st.spinner string with
        #                     # clearer message; spinner now properly wraps
        #                     # both extract AND reindex calls
        #                     with st.spinner(
        #                         "Extracting & indexing (no LLM tokens used)..."
        #                     ):
        #                         concepts      = extract_pdf_to_concepts(
        #                             uploaded_pdf.read(),
        #                             uploaded_pdf.name,
        #                         )
        #                         write_bundle(concepts)
        #                         newly_indexed = reindex_all()

        #                     st.success(
        #                         f"Ingested {len(concepts)} concept(s), "
        #                         f"indexed {newly_indexed}."
        #                     )
        #                     st.rerun()

        #         # CHANGED: spacer before clear button
        #         if doc_count > 0:
        #             section_spacer()
        #             if st.button(
        #                 "CLEAR KNOWLEDGE BASE",
        #                 use_container_width=True
        #             ):
        #                 removed = clear_all_bundles()
        #                 st.success(f"Cleared {removed} document(s)")
        #                 st.rerun()