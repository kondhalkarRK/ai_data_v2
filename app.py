# app.py - AI Data Platform V10
import streamlit as st

from config.settings   import init_session_state
from config.styles     import apply_styles
from core.join_engine  import get_working_df
from ui import sidebar, tab_join, tab_preview, tab_kpi, tab_query

# ── Semantic layer — use the real singleton getters ──────────────
from semantic.semantic_loader          import get_semantic_loader
from semantic.semantic_vector_search   import get_vector_search
from semantic.semantic_context_builder import get_context_builder
# ────────────────────────────────────────────────────────────────

from features.rag_query_memory       import glossary_store
from features.vector_schema_retrieval import schema_indexer

st.set_page_config(layout="wide", page_title="AI Data Platform", page_icon="🚀")

init_session_state()
apply_styles()

# ── Immediate boot screen — avoids any blank-screen moment while the
# semantic model / embedding engine (the slowest part of startup)
# loads. Cleared as soon as that init finishes below.
_boot_screen = st.empty()
_boot_screen.markdown(
    """
    <div class="boot-screen-overlay">
      <div class="ai-orb">
        <div class="ring ring1"></div>
        <div class="ring ring2"></div>
        <div class="core"></div>
      </div>
      <div class="boot-screen-title">Initializing AI Data Platform…</div>
      <div class="boot-screen-sub">Loading semantic model &amp; embedding engine</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Initialise semantic singletons ONCE at startup ───────────────
# get_*() functions handle their own lazy loading internally.
# We store them in session_state so every tab can access them
# without re-importing or re-building.


def _init_semantic_component(key: str, factory, warning_message: str):
    if st.session_state.get(key) is not None:
        return st.session_state.get(key)

    try:
        value = factory()
        st.session_state[key] = value
        return value
    except Exception as e:
        st.session_state[key] = None
        st.warning(f"⚠️ {warning_message}: {e}")
        return None


st.session_state.semantic_loader = _init_semantic_component(
    "semantic_loader",
    get_semantic_loader,
    "Semantic model not loaded",
)
st.session_state.semantic_search = _init_semantic_component(
    "semantic_search",
    get_vector_search,
    "Semantic vector search not ready",
)
st.session_state.semantic_builder = _init_semantic_component(
    "semantic_builder",
    get_context_builder,
    "Semantic context builder not ready",
)

# Initialise metric registry singleton
from core.metric_registry import get_metric_registry
_init_semantic_component(
    "metric_registry",
    get_metric_registry,
    "Metric registry not loaded",
)

# Store in session for tab access
if st.session_state.get("metric_registry"):
    st.session_state.metric_registry = (
        st.session_state.metric_registry
    )

# Initialise conversation state
try:
    from core.conversation_state import get_state as _get_conv_state
    if "conversation_state" not in st.session_state:
        _get_conv_state()  # initialises with empty state
except Exception:
    pass

# NOTE: We do NOT pre-build semantic_context here anymore.
# build_full_context(question, df) is per-question, not per-session.
# It is called inside tab_query.py at query-run time.
# ─────────────────────────────────────────────────────────────────

# ── Startup is done — clear the boot screen ───────────────────────
_boot_screen.empty()

# ═══════════════════════════════════════════════════════════════
# MAIN UI HEADER  (title + guide + theme)
# ═══════════════════════════════════════════════════════════════
_h1, _h2, _h3 = st.columns([5.4, 1.35, 1.55])
with _h1:
    st.markdown(
        """
        <div class="brand-title-stack">
          <div class="brand-eyebrow">🚀 AI DATA PLATFORM</div>
          <div class="brand-tagline">Decision Intelligence Workspace — governed insights, evidence, and shareable briefs</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with _h2:
    st.markdown(
        '<div class="brand-pill brand-pill-inline">⚡ GPT-4o · DuckDB</div>',
        unsafe_allow_html=True,
    )
with _h3:
    st.markdown('<div class="header-toolbar">', unsafe_allow_html=True)
    _guide_col, _theme_col = st.columns([0.38, 0.62], gap="small")
    with _guide_col:
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

**Tip:** Decision Room remembers your last query — use follow-up phrases instead of re-asking from scratch.
                """
            )
    with _theme_col:
        _theme_labels = {"light": "☀️ Light", "dark": "🌙 Dark", "ai": "✨ AI"}
        st.selectbox(
            "Appearance",
            options=list(_theme_labels.keys()),
            format_func=lambda k: _theme_labels[k],
            label_visibility="collapsed",
            key="ui_theme",
            help="Switch Light / Dark / AI appearance",
        )
    st.markdown("</div>", unsafe_allow_html=True)

sidebar.render()
if not st.session_state.dfs:
    st.info("👈 Upload one or more CSV files to get started.")
    st.stop()

glossary_store.seed_glossary_once()
try:
    from features.rag_query_memory import query_memory as _qm
    _qm.seed_golden_queries_once()
except Exception:
    pass

# Auto-seed India PV SOPs into OKF when the knowledge index is empty
# OKF disabled — re-enable via config.constants.OKF_ENABLED
try:
    from config.constants import OKF_ENABLED
except ImportError:
    OKF_ENABLED = False

if OKF_ENABLED and not st.session_state.get("_okf_autosseed_done"):
    try:
        from features.okf_knowledge.okf_answer import ensure_okf_ready
        ensure_okf_ready()
    except Exception:
        pass
    st.session_state["_okf_autosseed_done"] = True

tables     = list(st.session_state.dfs.keys())
working_df = get_working_df()

if working_df is not None and len(working_df.columns) > 25:
    schema_indexer.index_schema_columns(working_df, "df")

# ── Build base semantic context once per session after data loads ─
# build_base_context() is static (no question, no df needed).
# Stored so tab_query can append the per-question resolved context.
if (
    working_df is not None
    and "semantic_base_context" not in st.session_state
    and st.session_state.get("semantic_builder") is not None
):
    try:
        st.session_state.semantic_base_context = (
            st.session_state.semantic_builder.build_base_context()
        )
        st.session_state.semantic_column_map = (
            st.session_state.semantic_builder.build_physical_column_map(working_df)
        )
    except Exception:
        st.session_state.semantic_base_context = ""
        st.session_state.semantic_column_map   = ""
# ─────────────────────────────────────────────────────────────────

tab_join_ui, tab_preview_ui, tab_kpi_ui, tab_query_ui = st.tabs(
    ["🔗 Join / Combine", "📄 Data Preview", "📊 KPI Summary", "🏛️ Decision Room"]
)


def _render_tab_safely(tab_container, render_fn, label: str):
    """
    Run a tab's render() inside a safety boundary. If it raises, show a
    clean, contained error card in that tab instead of letting the
    exception propagate and crash the whole app with a raw traceback.
    """
    with tab_container:
        try:
            render_fn(working_df, tables, st.session_state.dfs)
        except Exception as e:
            st.error(f"⚠️ {label} hit an unexpected error and couldn't load.")
            with st.expander("Technical details"):
                st.code(str(e))
            st.caption(
                "The rest of the app is unaffected — try switching tabs "
                "or refreshing. If this keeps happening, use the 👎 "
                "feedback button to report it."
            )


_render_tab_safely(tab_join_ui,    tab_join.render,    "Join / Combine")
_render_tab_safely(tab_preview_ui, tab_preview.render, "Data Preview")
_render_tab_safely(tab_kpi_ui,     tab_kpi.render,     "KPI Summary")
_render_tab_safely(tab_query_ui,   tab_query.render,   "Decision Room")

st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#555;font-size:11px;'>"
    "🚀 Capgemini AI Data Platform &nbsp;|&nbsp; DuckDB · GPT-4o · Streamlit"
    "</div>",
    unsafe_allow_html=True,
)