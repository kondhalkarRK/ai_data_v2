"""
config/settings.py
"""
import os
import logging
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from langchain_openai import ChatOpenAI
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False


def _secret(name: str, default=None):
    """Streamlit Cloud secrets first, then env / .env."""
    try:
        val = st.secrets[name]
        if val not in (None, ""):
            return val
    except Exception:
        pass
    try:
        general = st.secrets["general"]
        val = general[name]
        if val not in (None, ""):
            return val
    except Exception:
        pass
    env = os.getenv(name)
    if env not in (None, ""):
        return env
    return default


def get_llm_config() -> dict:
    """Read LLM settings at call time (Streamlit Cloud secrets load correctly)."""
    return {
        "base_url": _secret(
            "CAPGEMINI_LLM_BASE_URL",
            "https://openai.generative.engine.capgemini.com/v1",
        ),
        "api_key": _secret("CAPGEMINI_LLM_API_KEY"),
        "model": _secret("CAPGEMINI_LLM_MODEL", "openai.gpt-5.1"),
    }


# Back-compat module-level names (lazy via get_llm_config when init runs)
LLM_BASE_URL = None
LLM_API_KEY = None
LLM_MODEL = None


@st.cache_resource(show_spinner=False)
def init_llm() -> object | None:
    """
    Initialize and cache the LLM client for the Streamlit session.
    Returns None if the LLM package is unavailable or initialization fails,
    so calling code should handle the None case gracefully.
    """
    global LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

    cfg = get_llm_config()
    LLM_BASE_URL = cfg["base_url"]
    LLM_API_KEY = cfg["api_key"]
    LLM_MODEL = cfg["model"]

    if not _LLM_AVAILABLE:
        logger.warning("langchain_openai is not installed; LLM features disabled.")
        st.session_state["_llm_init_error"] = "langchain-openai package not installed"
        return None

    if not LLM_API_KEY:
        logger.error(
            "CAPGEMINI_LLM_API_KEY is not set. Add it in Streamlit Cloud "
            "Settings → Secrets, or in a local .env file."
        )
        st.session_state["_llm_init_error"] = (
            "CAPGEMINI_LLM_API_KEY missing — add it in Streamlit "
            "Settings → Secrets (see secrets.example.toml)"
        )
        return None

    try:
        llm = ChatOpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
            default_headers={"x-api-key": LLM_API_KEY},
            model=LLM_MODEL,
            temperature=0,
            max_completion_tokens=600,
            timeout=55,
            max_retries=1,
        )
        st.session_state.pop("_llm_init_error", None)
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}", exc_info=True)
        st.session_state["_llm_init_error"] = f"LLM init failed: {e}"
        return None


# ─────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────
DEFAULTS = {
    "dfs": {}, "join_mode": "auto",
    "manual_joins": {}, "sql_join_text": "",
    "memory": {},
    "last_query": "", "last_plan": None,
    "llm_calls": 0, "total_tokens": 0,
    "max_llm_calls": 60,
    "auto_join_base": None,
    "ui_theme": "dark",  # light | dark | ai
}

def init_session_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Conversation state
    if "conversation_state" not in st.session_state:
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

    # Evidence tracking
    if "execution_evidence" not in st.session_state:
        st.session_state.execution_evidence = []

    # Query path stats
    if "query_stats" not in st.session_state:
        st.session_state.query_stats = {
            "deterministic": 0,
            "fallback": 0,
            "cache": 0,
        }

    if "pinned_decisions" not in st.session_state:
        st.session_state.pinned_decisions = []