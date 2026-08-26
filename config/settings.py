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


def _section_secret(section: str, name: str, env_name: str, default=None):
    """Read a nested Streamlit secret, then fall back to an environment key."""
    try:
        value = st.secrets[section][name]
        if value not in (None, ""):
            return value
    except Exception:
        pass
    return _secret(env_name, default)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def is_streamlit_cloud() -> bool:
    """True when running on Streamlit Community Cloud (not local `streamlit run`)."""
    if _as_bool(os.getenv("IS_STREAMLIT_CLOUD"), False):
        return True
    if os.getenv("STREAMLIT_RUNTIME_ENV", "").strip().lower() == "cloud":
        return True
    # Community Cloud mounts the repo under /mount/src
    if os.path.isdir("/mount/src"):
        return True
    return False


def is_loopback_host(host: str | None) -> bool:
    h = (host or "").strip().lower()
    return h in {"", "localhost", "127.0.0.1", "::1"}


def get_data_config() -> dict:
    """Return backend configuration without exposing credentials to the UI."""
    backend = str(_secret("DATA_BACKEND", "csv_duckdb")).strip().lower()
    if backend not in {"csv_duckdb", "postgres"}:
        logger.warning("Unknown DATA_BACKEND=%s; using csv_duckdb.", backend)
        backend = "csv_duckdb"

    # Default SSL: prefer locally; require on Streamlit Cloud (managed Postgres).
    default_ssl = "require" if is_streamlit_cloud() else "prefer"
    # Fall back to CSV/DuckDB when Postgres is unreachable (needed for Streamlit Cloud
    # when secrets still point at localhost, or the remote DB is down).
    fallback_csv = _as_bool(
        _secret("POSTGRES_FALLBACK_CSV", "true"),
        True,
    )

    return {
        "backend": backend,
        "industry_pack": str(
            _secret("INDUSTRY_PACK", "insurance" if backend == "postgres" else "automotive")
        ).strip().lower(),
        "postgres_fallback_csv": fallback_csv,
        "postgres": {
            # Optional full URL (Neon/Supabase/etc.). When set, host/user/password are ignored.
            "connection_url": _section_secret(
                "postgres", "connection_url", "POSTGRES_URL", ""
            )
            or _section_secret(
                "postgres", "url", "DATABASE_URL", ""
            ),
            "host": _section_secret("postgres", "host", "POSTGRES_HOST", "localhost"),
            "port": _as_int(
                _section_secret("postgres", "port", "POSTGRES_PORT", 5432),
                5432,
            ),
            "database": _section_secret(
                "postgres", "database", "POSTGRES_DATABASE", "askdb_dev"
            ),
            "user": _section_secret(
                "postgres", "user", "POSTGRES_USER", "askdb_app"
            ),
            "password": _section_secret(
                "postgres", "password", "POSTGRES_PASSWORD"
            ),
            "schema": _section_secret(
                "postgres", "schema", "POSTGRES_SCHEMA", "insurance"
            ),
            "sslmode": _section_secret(
                "postgres", "sslmode", "POSTGRES_SSLMODE", default_ssl
            ),
            "connect_timeout_seconds": _as_int(
                _section_secret(
                    "postgres",
                    "connect_timeout_seconds",
                    "POSTGRES_CONNECT_TIMEOUT_SECONDS",
                    10,
                ),
                10,
            ),
            "statement_timeout_seconds": _as_int(
                _section_secret(
                    "postgres",
                    "statement_timeout_seconds",
                    "POSTGRES_STATEMENT_TIMEOUT_SECONDS",
                    30,
                ),
                30,
            ),
            "max_result_rows": _as_int(
                _section_secret(
                    "postgres",
                    "max_result_rows",
                    "POSTGRES_MAX_RESULT_ROWS",
                    1000,
                ),
                1000,
            ),
            "pool_min_size": _as_int(
                _section_secret(
                    "postgres", "pool_min_size", "POSTGRES_POOL_MIN_SIZE", 1
                ),
                1,
            ),
            "pool_max_size": _as_int(
                _section_secret(
                    "postgres", "pool_max_size", "POSTGRES_POOL_MAX_SIZE", 5
                ),
                5,
            ),
        },
    }


def get_llm_config() -> dict:
    """Read LLM settings at call time (Streamlit Cloud secrets load correctly)."""
    from config.llm_catalog import (
        DEFAULT_FAMILY,
        DEFAULT_TEMPERATURE,
        DEFAULT_TIER,
        get_profile,
    )

    family = DEFAULT_FAMILY
    tier = DEFAULT_TIER
    temperature = DEFAULT_TEMPERATURE
    model_id = None
    try:
        family = str(st.session_state.get("llm_family") or DEFAULT_FAMILY)
        tier = str(st.session_state.get("llm_tier") or DEFAULT_TIER)
        temperature = float(st.session_state.get("llm_temperature") or DEFAULT_TEMPERATURE)
        model_id = st.session_state.get("llm_model_id")
    except Exception:
        pass

    profile = get_profile(family, tier, model_id)
    secret_model = _secret("CAPGEMINI_LLM_MODEL")
    model = profile["model"]
    # Keep secrets model when user has not opened LLM settings yet.
    try:
        if not st.session_state.get("_llm_profile_chosen") and secret_model:
            model = str(secret_model)
    except Exception:
        if secret_model:
            model = str(secret_model)

    return {
        "base_url": _secret(
            "CAPGEMINI_LLM_BASE_URL",
            "https://openai.generative.engine.capgemini.com/v1",
        ),
        "api_key": _secret("CAPGEMINI_LLM_API_KEY"),
        "model": model,
        "family": family,
        "tier": tier,
        "temperature": max(0.0, min(1.5, temperature)),
        "usd_per_1m": profile["usd_per_1m"],
        "label": profile["label"],
    }


# Back-compat module-level names (lazy via get_llm_config when init runs)
LLM_BASE_URL = None
LLM_API_KEY = None
LLM_MODEL = None


@st.cache_resource(show_spinner=False)
def init_llm(model: str, temperature: float) -> object | None:
    """
    Initialize and cache the LLM client for the Streamlit session.
    Returns None if the LLM package is unavailable or initialization fails,
    so calling code should handle the None case gracefully.
    """
    global LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

    cfg = get_llm_config()
    LLM_BASE_URL = cfg["base_url"]
    LLM_API_KEY = cfg["api_key"]
    LLM_MODEL = model or cfg["model"]

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
            temperature=float(temperature),
            max_completion_tokens=600,
            timeout=55,
            max_retries=1,
        )
        st.session_state.pop("_llm_init_error", None)
        return llm
    except Exception as e:
        logger.exception("Failed to initialize LLM client")
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
    "max_llm_tokens": 30_000,
    "llm_usage_log": [],
    "llm_family": "gpt",
    "llm_tier": "high",
    "llm_model_id": "openai.gpt-5.1",
    "llm_temperature": 0.2,
    "llm_est_usd": 0.0,
    "auto_join_base": None,
    "ui_theme": "dark",  # light | dark | ai
    "data_backend": "csv_duckdb",
}

def init_session_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Secrets/environment select the startup backend. A future UI selector may
    # override this per session without changing the configured default.
    if not st.session_state.get("_data_backend_configured"):
        st.session_state.data_backend = get_data_config()["backend"]
        st.session_state["_data_backend_configured"] = True

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