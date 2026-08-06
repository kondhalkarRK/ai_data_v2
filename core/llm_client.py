"""
core/llm_client.py
"""
import streamlit as st

from config.settings import init_llm, get_llm_config


def _get_llm():
    """Lazy init so Streamlit Cloud secrets are read after app boot."""
    return init_llm()


def call_llm(prompt: str) -> str | None:
    return _invoke_llm(prompt, max_completion_tokens=600)


def call_llm_narration(prompt: str) -> str | None:
    """Compact narration budget — use only when explicitly enabled or requested."""
    try:
        from config.constants import NARRATION_MAX_COMPLETION_TOKENS
    except ImportError:
        NARRATION_MAX_COMPLETION_TOKENS = 400
    return _invoke_llm(prompt, max_completion_tokens=NARRATION_MAX_COMPLETION_TOKENS)


def _invoke_llm(prompt: str, *, max_completion_tokens: int) -> str | None:
    llm = _get_llm()
    if llm is None:
        reason = st.session_state.get("_llm_init_error") or "Unknown configuration issue"
        cfg = get_llm_config()
        has_key = bool(cfg.get("api_key"))
        st.error(
            f"LLM not configured. {reason}"
            + ("" if has_key else " Add CAPGEMINI_LLM_API_KEY in Streamlit Settings → Secrets, then Reboot app.")
        )
        return None
    if st.session_state.llm_calls >= st.session_state.max_llm_calls:
        st.error("🚫 LLM call limit reached.")
        return None
    try:
        bound = llm.bind(max_completion_tokens=max_completion_tokens)
        resp = bound.invoke(prompt)
    except Exception:
        try:
            resp = llm.invoke(prompt)
        except Exception as e:
            st.error(f"⚠️ AI service call failed: {e}")
            return None
    text = getattr(resp, "content", str(resp))
    st.session_state.llm_calls   += 1
    st.session_state.total_tokens += int((len(prompt)+len(text))/4)
    return text
