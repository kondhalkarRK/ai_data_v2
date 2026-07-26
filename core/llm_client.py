"""
core/llm_client.py
"""
import streamlit as st

from config.settings import init_llm

# ─────────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────────
llm = init_llm()

def call_llm(prompt: str) -> str | None:
    if llm is None:
        st.error("LLM not configured.")
        return None
    if st.session_state.llm_calls >= st.session_state.max_llm_calls:
        st.error("🚫 LLM call limit reached.")
        return None
    try:
        resp = llm.invoke(prompt)
    except Exception as e:
        st.error(f"⚠️ AI service call failed: {e}")
        return None
    text = getattr(resp, "content", str(resp))
    st.session_state.llm_calls   += 1
    st.session_state.total_tokens += int((len(prompt)+len(text))/4)
    return text
