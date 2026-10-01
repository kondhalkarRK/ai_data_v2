"""LLM completion with retries, circuit breaker, and model fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import Industry, Settings
from app.services.governance.llm_config import active_llm, endpoint

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LlmResult:
    sql: str | None
    narrative: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    timed_out: bool = False
    circuit_open: bool = False
    content: str = ""


class _CircuitBreaker:
    """Fail fast when the LLM provider is clearly degraded."""

    def __init__(self, *, failure_threshold: int = 3, cooldown_seconds: float = 45) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self.cooldown_seconds:
            self._opened_at = None
            self._failures = 0
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._opened_at = time.monotonic()


_CIRCUIT = _CircuitBreaker()


def _slim_system_prompt(
    industry: Industry,
    schema_hints: str | None,
    prior_sql: str | None = None,
    feedback: str | None = None,
) -> str:
    hints = (schema_hints or "").strip()
    hint_block = f"\nDomain context (use only this):\n{hints}\n" if hints else "\n"
    prior_block = ""
    if prior_sql:
        prior_block = (
            "\nPRIOR SUCCESSFUL SQL (preserve its intent, joins, and filters unless "
            f"the user explicitly changes them):\n{prior_sql[:1800]}\n"
        )
    if feedback:
        prior_block += (
            "\nYOUR PREVIOUS SQL WAS REJECTED BY THE VALIDATOR. Fix exactly this and "
            f"return the corrected SELECT only:\n{feedback[:2400]}\n"
        )
    return (
        f"You are Ask DB for {industry.value} analytics. "
        "Return one PostgreSQL SELECT only — schema-qualified, read-only, "
        "LIMIT <= 50. No markdown, no commentary. "
        "Obey Resolved entity, Mandatory filters, ALWAYS/NEVER rules exactly. "
        "Never invent tables or columns. Never confuse salesperson (dim_salesman) "
        "with dealer (dim_dealer)."
        f"{hint_block}{prior_block}"
    )


def _extract_sql(content: str) -> str | None:
    sql = (content or "").strip()
    if not sql:
        return None
    if sql.startswith("```"):
        sql = sql.strip("`")
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()
    return sql or None


async def _one_completion(
    *,
    settings: Settings,
    model: str,
    system: str,
    question: str,
    timeout: float,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    max_tokens: int = 400,
) -> LlmResult:
    governed = active_llm(settings)
    target = endpoint(settings, governed.provider)
    if target is None:
        return LlmResult(sql=None, narrative="", model=model, error="No LLM API key configured")
    base_url, auth_headers = target
    payload: dict[str, object] = {
        "model": model,
        "temperature": governed.temperature if temperature is None else temperature,
        "max_tokens": min(governed.max_tokens, max_tokens),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    }
    if top_p is not None:
        payload["top_p"] = top_p
    # Top-K is provider-specific; only send when the selected model advertises support.
    if top_k is not None and _model_supports_top_k(model):
        payload["top_k"] = top_k
    headers = {**auth_headers, "Content-Type": "application/json"}
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
    except httpx.TimeoutException:
        return LlmResult(
            sql=None,
            narrative="",
            model=model,
            error="Timeout",
            timed_out=True,
        )
    except Exception as exc:
        return LlmResult(
            sql=None,
            narrative="",
            model=model,
            error=f"{type(exc).__name__}: {exc}"[:240],
        )

    choice = (body.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    usage = body.get("usage") or {}
    sql = _extract_sql(content)
    return LlmResult(
        sql=sql,
        narrative="SQL was generated by the language model and validated by guardrails.",
        model=body.get("model") or model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        error=None if sql else "Invalid model response (empty SQL)",
        content=content,
    )


def _model_supports_top_k(model: str) -> bool:
    lowered = model.casefold()
    # OpenAI chat-completions style models generally do not accept top_k.
    if "openai" in lowered or "gpt-" in lowered:
        return False
    return True


def model_catalog(settings: Settings) -> list[dict[str, object]]:
    primary = active_llm(settings).model
    fallback = (settings.llm_fallback_model or "").strip()
    models = [primary]
    if fallback and fallback not in models:
        models.append(fallback)
    return [
        {
            "id": model,
            "label": model,
            "supportsTopP": True,
            "supportsTopK": _model_supports_top_k(model),
            "typicalCostPerQueryUsd": 0.002 if "gpt-5" in model else 0.0015,
        }
        for model in models
    ]


async def complete_chat(
    *,
    settings: Settings,
    industry: Industry,
    question: str,
    schema_hints: str | None = None,
    prior_sql: str | None = None,
    model_override: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    feedback: str | None = None,
) -> LlmResult:
    governed = active_llm(settings)
    if not llm_configured(settings):
        return LlmResult(
            sql=None,
            narrative="",
            model=governed.model,
            error="No LLM API key configured",
        )

    if not _CIRCUIT.allow():
        return LlmResult(
            sql=None,
            narrative="The language model provider is temporarily unavailable.",
            model=governed.model,
            error="AI service is currently degraded",
            circuit_open=True,
        )

    timeout = float(settings.nlq_llm_timeout_seconds)
    system = _slim_system_prompt(industry, schema_hints, prior_sql, feedback)
    primary = (model_override or "").strip() or governed.model
    # The environment fallback model only exists on the default (OpenAI) endpoint.
    fallback = (
        (settings.llm_fallback_model or "").strip() or None
        if governed.provider == "openai"
        else None
    )

    attempts: list[str] = [primary]
    if fallback and fallback != primary:
        attempts.append(fallback)

    last: LlmResult | None = None
    for model_index, model in enumerate(attempts):
        retries = 1 + (0 if model_index else settings.nlq_llm_max_retries)
        for attempt in range(retries):
            result = await _one_completion(
                settings=settings,
                model=model,
                system=system,
                question=question,
                timeout=timeout,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            )
            last = result
            if result.sql:
                _CIRCUIT.record_success()
                return result
            transient = result.timed_out or (
                result.error
                and any(
                    token in result.error.lower()
                    for token in ("5", "timeout", "unavailable", "connect")
                )
            )
            if not transient:
                break
            if attempt + 1 < retries:
                await asyncio.sleep(0.4 * (2**attempt))
        # Fall through to next model on repeated primary failure.
        logger.info("LLM model %s failed; trying next if available", model)

    _CIRCUIT.record_failure()
    assert last is not None
    if last.circuit_open:
        return last
    return LlmResult(
        sql=None,
        narrative=last.narrative or f"The language model call failed: {last.error or 'unknown'}.",
        model=last.model,
        prompt_tokens=last.prompt_tokens,
        completion_tokens=last.completion_tokens,
        error=last.error or "Unavailable",
        timed_out=last.timed_out,
    )


async def complete_text(
    *,
    settings: Settings,
    system: str,
    user: str,
    max_tokens: int = 200,
    model_override: str | None = None,
) -> LlmResult:
    """One short non-SQL completion (question interpretation). Never retried."""
    model = (model_override or "").strip() or active_llm(settings).model
    if not llm_configured(settings):
        return LlmResult(sql=None, narrative="", model=model, error="No LLM API key configured")
    if not _CIRCUIT.allow():
        return LlmResult(
            sql=None, narrative="", model=model, error="AI service is currently degraded",
            circuit_open=True,
        )
    result = await _one_completion(
        settings=settings,
        model=model,
        system=system,
        question=user,
        timeout=float(settings.nlq_llm_timeout_seconds),
        temperature=0.0,
        max_tokens=max_tokens,
    )
    if result.content:
        _CIRCUIT.record_success()
    elif result.timed_out or result.error:
        _CIRCUIT.record_failure()
    return result


def llm_configured(settings: Settings) -> bool:
    return endpoint(settings, active_llm(settings).provider) is not None


def circuit_stats() -> dict[str, object]:
    return {
        "open": not _CIRCUIT.allow(),
        "failures": _CIRCUIT._failures,
        "openedAt": _CIRCUIT._opened_at,
    }
