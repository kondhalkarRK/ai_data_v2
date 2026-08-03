"""
config/settings.py
"""
import os
import logging
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from langchain_openai import ChatOpenAI
    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────────

# Load sensitive/configurable values from environment (.env) instead of hardcoding
LLM_BASE_URL = os.getenv("CAPGEMINI_LLM_BASE_URL", "https://openai.generative.engine.capgemini.com/v1")
LLM_API_KEY = os.getenv("CAPGEMINI_LLM_API_KEY")
LLM_MODEL = os.getenv("CAPGEMINI_LLM_MODEL", "openai.gpt-5.1")


@st.cache_resource(show_spinner=False)
def init_llm() -> object | None:
    """
    Initialize and cache the LLM client for the Streamlit session.
    Returns None if the LLM package is unavailable or initialization fails,
    so calling code should handle the None case gracefully.
    """
    if not _LLM_AVAILABLE:
        logger.warning("langchain_openai is not installed; LLM features disabled.")
        return None

    if not LLM_API_KEY:
        logger.error(
            "CAPGEMINI_LLM_API_KEY is not set. Add it to your .env file "
            "or environment variables before starting the app."
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
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}", exc_info=True)
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