# app.py - ASK - DB
import streamlit as st
import pandas as pd

from config.settings   import get_data_config, init_session_state
from config.styles     import apply_styles
from core.data_backend.factory import (
    ensure_data_backend_ready,
    get_backend,
    postgres_mode_enabled,
)
from core.join_engine  import get_working_df
from ui import sidebar, tab_preview, tab_kpi, tab_query

# ── Semantic layer — use the real singleton getters ──────────────
from semantic.semantic_loader          import get_semantic_loader
from semantic.semantic_vector_search   import get_vector_search
from semantic.semantic_context_builder import get_context_builder
# ────────────────────────────────────────────────────────────────

from features.rag_query_memory       import glossary_store
from features.vector_schema_retrieval import schema_indexer

st.set_page_config(layout="wide", page_title="ASK - DB", page_icon="💬")

init_session_state()
apply_styles()

# Resolve Postgres vs CSV early. Streamlit Cloud cannot use host=localhost;
# we soft-fallback to csv_duckdb so the hosted app still boots.
_backend_ready, _backend_status = ensure_data_backend_ready()
if not _backend_ready:
    st.error(f"PostgreSQL connection is not ready: {_backend_status}")
    st.info(
        "For local: start Postgres and set [postgres] in .streamlit/secrets.toml. "
        "For Streamlit Cloud: use a reachable managed Postgres host/connection_url "
        "(not localhost), or set DATA_BACKEND = \"csv_duckdb\"."
    )
    st.stop()
_fallback_reason = st.session_state.get("_postgres_fallback_reason")
if _fallback_reason and not st.session_state.get("_postgres_fallback_shown"):
    st.warning(
        "Running in CSV/DuckDB mode — PostgreSQL was not reachable.\n\n"
        f"{_fallback_reason}"
    )
    st.session_state["_postgres_fallback_shown"] = True

# PostgreSQL insurance deployments start with the configured semantic pack
# before any semantic singleton is built.
if postgres_mode_enabled():
    try:
        from semantic.industry_packs import activate_pack, get_active_pack_id

        _configured_pack = get_data_config().get("industry_pack") or "insurance"
        if get_active_pack_id() != _configured_pack:
            _pack_ok, _pack_message = activate_pack(_configured_pack)
            if not _pack_ok:
                st.warning(f"Industry pack not activated: {_pack_message}")
    except Exception as _pack_error:
        st.warning(f"Industry pack initialization failed: {_pack_error}")

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
      <div class="boot-screen-title">Initializing ASK - DB…</div>
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

sidebar.render()
_postgres_mode = postgres_mode_enabled()
if not _postgres_mode and not st.session_state.dfs:
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

if _postgres_mode:
    tables = get_backend().list_tables()
    working_df = pd.DataFrame()
else:
    tables = list(st.session_state.dfs.keys())
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

tab_preview_ui, tab_kpi_ui, tab_query_ui = st.tabs(
    ["📄 Data Preview", "📊 KPI Summary", "💬 Chat Room"]
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


_render_tab_safely(tab_preview_ui, tab_preview.render, "Data Preview")
_render_tab_safely(tab_kpi_ui,     tab_kpi.render,     "KPI Summary")
_render_tab_safely(tab_query_ui,   tab_query.render,   "Chat Room")

st.markdown("---")
st.markdown(
    "<div class='app-footer'>"
    f"ASK - DB &nbsp;·&nbsp; {'PostgreSQL' if _postgres_mode else 'DuckDB'} "
    "· AI Data Copilot · Streamlit"
    "</div>",
    unsafe_allow_html=True,
)