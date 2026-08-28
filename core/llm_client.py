"""
core/llm_client.py
Session-scoped LLM calls with call + token budgets and usage log.
"""
from __future__ import annotations

import time

import streamlit as st

from config.settings import init_llm, get_llm_config


def _get_llm():
    """Lazy init so Streamlit Cloud secrets are read after app boot."""
    cfg = get_llm_config()
    return init_llm(str(cfg.get("model") or ""), float(cfg.get("temperature") or 0))


def _ensure_usage_defaults() -> None:
    if "llm_calls" not in st.session_state:
        st.session_state.llm_calls = 0
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    if "max_llm_calls" not in st.session_state:
        st.session_state.max_llm_calls = 60
    if "max_llm_tokens" not in st.session_state:
        st.session_state.max_llm_tokens = 30_000
    if "llm_usage_log" not in st.session_state:
        st.session_state.llm_usage_log = []
    if "llm_est_usd" not in st.session_state:
        st.session_state.llm_est_usd = 0.0


def _extract_usage_tokens(resp, prompt: str, text: str) -> tuple[int, int, int]:
    """Return (prompt_tokens, completion_tokens, total). Prefer provider metadata."""
    prompt_tok = None
    completion_tok = None
    total_tok = None

    meta_candidates = []
    for attr in ("usage_metadata", "response_metadata"):
        raw = getattr(resp, attr, None)
        if isinstance(raw, dict):
            meta_candidates.append(raw)
            usage = raw.get("token_usage") or raw.get("usage")
            if isinstance(usage, dict):
                meta_candidates.append(usage)

    for meta in meta_candidates:
        if not isinstance(meta, dict):
            continue
        if prompt_tok is None:
            for k in ("input_tokens", "prompt_tokens", "prompt_token_count"):
                if k in meta and meta[k] is not None:
                    try:
                        prompt_tok = int(meta[k])
                        break
                    except (TypeError, ValueError):
                        pass
        if completion_tok is None:
            for k in ("output_tokens", "completion_tokens", "completion_token_count"):
                if k in meta and meta[k] is not None:
                    try:
                        completion_tok = int(meta[k])
                        break
                    except (TypeError, ValueError):
                        pass
        if total_tok is None and meta.get("total_tokens") is not None:
            try:
                total_tok = int(meta["total_tokens"])
            except (TypeError, ValueError):
                pass

    if prompt_tok is None:
        prompt_tok = max(1, int(len(prompt or "") / 4))
    if completion_tok is None:
        completion_tok = max(0, int(len(text or "") / 4))
    if total_tok is None:
        total_tok = prompt_tok + completion_tok
    return prompt_tok, completion_tok, total_tok


def call_llm(prompt: str, *, purpose: str = "sql") -> str | None:
    return _invoke_llm(prompt, max_completion_tokens=600, purpose=purpose)


def call_llm_narration(prompt: str, *, purpose: str = "narration") -> str | None:
    """Compact narration budget — use only when explicitly enabled or requested."""
    try:
        from config.constants import NARRATION_MAX_COMPLETION_TOKENS
    except ImportError:
        NARRATION_MAX_COMPLETION_TOKENS = 400
    return _invoke_llm(
        prompt,
        max_completion_tokens=NARRATION_MAX_COMPLETION_TOKENS,
        purpose=purpose or "narration",
    )


def _invoke_llm(
    prompt: str,
    *,
    max_completion_tokens: int,
    purpose: str = "other",
) -> str | None:
    _ensure_usage_defaults()
    llm = _get_llm()
    if llm is None:
        reason = st.session_state.get("_llm_init_error") or "Unknown configuration issue"
        cfg = get_llm_config()
        has_key = bool(cfg.get("api_key"))
        st.error(
            f"LLM not configured. {reason}"
            + (
                ""
                if has_key
                else " Add CAPGEMINI_LLM_API_KEY in Streamlit Settings → Secrets, then Reboot app."
            )
        )
        return None

    max_calls = max(int(st.session_state.get("max_llm_calls") or 60), 1)
    max_tokens = max(int(st.session_state.get("max_llm_tokens") or 30_000), 1)
    if st.session_state.llm_calls >= max_calls:
        st.error("🚫 LLM call limit reached (Calls / 60).")
        return None
    if int(st.session_state.total_tokens or 0) >= max_tokens:
        st.error("🚫 LLM token budget reached (Tokens / 30K).")
        return None

    t0 = time.perf_counter()
    try:
        from core.observability import span as obs_span
    except Exception:
        obs_span = None

    def _do_invoke():
        try:
            bound = llm.bind(max_completion_tokens=max_completion_tokens)
            return bound.invoke(prompt)
        except Exception:
            return llm.invoke(prompt)

    rec = {"attrs": {}}
    resp = None
    try:
        if obs_span is not None:
            with obs_span(f"llm.{purpose or 'other'}", prompt_chars=len(prompt or "")) as rec:
                rec.setdefault("attrs", {})["prompt_chars"] = len(prompt or "")
                resp = _do_invoke()
        else:
            resp = _do_invoke()
    except Exception as e:
        st.error(f"⚠️ AI service call failed: {e}")
        return None

    text = getattr(resp, "content", str(resp))
    prompt_tok, completion_tok, total_tok = _extract_usage_tokens(resp, prompt, text)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    if isinstance(rec, dict):
        rec.setdefault("attrs", {})["tokens"] = total_tok
        rec.setdefault("attrs", {})["duration_ms"] = duration_ms

    # Soft-clamp remaining budget
    remaining = max_tokens - int(st.session_state.total_tokens or 0)
    if total_tok > remaining:
        total_tok = max(0, remaining)

    st.session_state.llm_calls += 1
    st.session_state.total_tokens = int(st.session_state.total_tokens or 0) + total_tok

    entry = {
        "purpose": purpose or "other",
        "prompt_tokens_est": prompt_tok,
        "completion_tokens_est": completion_tok,
        "total_tokens_est": total_tok,
        "ts": time.time(),
        "duration_ms": duration_ms,
        "prompt_chars": len(prompt or ""),
    }
    log = list(st.session_state.get("llm_usage_log") or [])
    log.append(entry)
    st.session_state.llm_usage_log = log[-40:]

    try:
        from config.llm_catalog import estimate_usd

        cfg = get_llm_config()
        st.session_state.llm_est_usd = float(
            st.session_state.get("llm_est_usd") or 0
        ) + estimate_usd(total_tok, float(cfg.get("usd_per_1m") or 0))
    except Exception:
        pass
    return text


def usage_caption() -> str:
    """Compact read-only usage line for composer / status."""
    _ensure_usage_defaults()
    calls = int(st.session_state.get("llm_calls") or 0)
    tokens = int(st.session_state.get("total_tokens") or 0)
    max_calls = max(int(st.session_state.get("max_llm_calls") or 60), 1)
    max_tokens = max(int(st.session_state.get("max_llm_tokens") or 30_000), 1)
    tok_label = f"{tokens:,}" if tokens < 1000 else f"{tokens / 1000:.1f}K".replace(".0K", "K")
    max_tok_label = f"{max_tokens // 1000}K" if max_tokens >= 1000 else str(max_tokens)
    return f"LLM usage {calls}/{max_calls} · Tokens {tok_label}/{max_tok_label}"
