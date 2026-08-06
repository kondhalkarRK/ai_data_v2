"""
ui/sidebar.py
"""

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
    from features.okf_knowledge.pdf_extractor import extract_pdf_to_concepts, pdf_extraction_available
    from features.okf_knowledge.okf_store import write_bundle, list_bundles, clear_all_bundles
    from features.okf_knowledge.okf_retriever import reindex_all, indexed_concept_count, clear_index
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

            if st.button("RESET", use_container_width=True, key="sidebar_reset"):
                st.session_state.llm_calls    = 0
                st.session_state.total_tokens = 0
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)

        # =========================
        # SAVED QUESTIONS (LLM cost saver)
        # =========================
        with st.container(border=True):
            st.markdown('<div class="sb-views-wrap">', unsafe_allow_html=True)
            section_title("💾 SAVED QUESTIONS")
            section_spacer()

            saved_count = cache_store.count_active()

            status_row("Saved", saved_count, "#a5b4fc")

            section_spacer()

            with st.expander("Recent saved questions", expanded=False):
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

        # =========================
        # KNOWLEDGE BASE — OKF
        # =========================
        if _OKF_AVAILABLE:
            with st.container(border=True):
                section_title("📚 KNOWLEDGE BASE (OKF)")
                section_spacer()

                bundles = list_bundles()
                doc_count = len(bundles)
                concept_count = indexed_concept_count()

                c1, c2 = st.columns(2)
                with c1:
                    status_row("Docs", doc_count, "#38bdf8")
                with c2:
                    status_row("Concepts", concept_count, "#38bdf8")

                section_spacer()
                st.caption(
                    "Business documents (handbooks, targets, strategy, SOPs) in "
                    "doc/business_knowledge/ — separate from business_glossary.yaml."
                )

                if st.button(
                    "SEED BUSINESS DOCUMENTS",
                    use_container_width=True,
                    key="okf_seed_sops",
                ):
                    with st.spinner("Seeding handbooks, targets, strategy & SOPs…"):
                        try:
                            from features.okf_knowledge.okf_bootstrap import (
                                bootstrap_business_knowledge,
                            )
                            summary = bootstrap_business_knowledge(force=True)
                            st.success(
                                f"Seeded {summary.get('docs', 0)} doc(s), "
                                f"{summary.get('concepts', 0)} concepts, "
                                f"indexed {summary.get('indexed', 0)}."
                            )
                        except Exception as e:
                            st.error(f"Seed failed: {e}")
                    st.rerun()

                uploaded_kb = st.file_uploader(
                    "Add business PDF or Markdown",
                    type=["pdf", "md", "markdown", "txt"],
                    label_visibility="collapsed",
                    key="okf_pdf_upload",
                )

                if uploaded_kb is not None:
                    if st.button(
                        "INGEST INTO KNOWLEDGE BASE",
                        use_container_width=True,
                        key="okf_ingest_btn",
                    ):
                        with st.spinner("Extracting and indexing (no LLM tokens used)..."):
                            try:
                                name = uploaded_kb.name
                                raw = uploaded_kb.read()
                                if name.lower().endswith((".md", ".markdown", ".txt")):
                                    from features.okf_knowledge.md_extractor import (
                                        extract_markdown_to_concepts,
                                    )
                                    text = (
                                        raw.decode("utf-8-sig")
                                        if isinstance(raw, bytes)
                                        else str(raw)
                                    )
                                    concepts = extract_markdown_to_concepts(text, name)
                                else:
                                    if not pdf_extraction_available():
                                        st.error("Install pypdf to ingest PDFs.")
                                        concepts = []
                                    else:
                                        concepts = extract_pdf_to_concepts(raw, name)
                                if concepts:
                                    write_bundle(concepts)
                                    newly_indexed = reindex_all()
                                    st.success(
                                        f"Ingested {len(concepts)} concept(s), "
                                        f"indexed {newly_indexed}."
                                    )
                                else:
                                    st.warning("No concepts extracted from file.")
                            except Exception as e:
                                st.error(str(e))
                        st.rerun()

                if doc_count > 0:
                    section_spacer()
                    with st.expander(f"Ingested docs ({doc_count})", expanded=False):
                        for b in bundles[:12]:
                            st.caption(
                                f"• {b.get('source_doc')} "
                                f"({b.get('concept_count')} concepts)"
                            )
                    if st.button(
                        "CLEAR KNOWLEDGE BASE",
                        use_container_width=True,
                        key="okf_clear_btn",
                    ):
                        removed = clear_all_bundles()
                        try:
                            clear_index()
                        except Exception:
                            pass
                        st.success(f"Cleared {removed} document(s)")
                        st.rerun()
        else:
            with st.container(border=True):
                section_title("📚 KNOWLEDGE BASE")
                st.caption("OKF modules unavailable — check features/okf_knowledge.")

