"""One ordinary provider call at a time, quota governed and usage accounted."""

import asyncio
import time

from app.core.exceptions import QuotaExceededError
from app.models.activity import LlmUsage
from app.schemas.bi import BiUsage
from app.services.analytics.runner import AnalyticsService
from app.services.governance import enforce_quota, sync_llm_config
from app.services.governance.llm_catalog import load_catalog
from app.services.governance.llm_config import active_llm
from app.services.llm import complete_text, llm_configured


class BiProviderError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class BiCompletion:
    def __init__(self, base: AnalyticsService, limit: int = 2):
        self.base = base
        self.limit = limit
        self.usage = BiUsage()

    async def call(self, system: str, prompt: str, max_tokens: int = 3200) -> str:
        if self.usage.llm_calls >= self.limit:
            raise BiProviderError("budget", "This request reached its AI processing limit.")
        try:
            await enforce_quota(self.base._app, self.base._user)
        except QuotaExceededError as exc:
            raise BiProviderError(
                "quota", "Your AI allowance is exhausted. Existing reports remain usable."
            ) from exc
        await sync_llm_config(self.base._app, self.base._settings)
        if not llm_configured(self.base._settings):
            raise BiProviderError(
                "provider_unavailable",
                "AI is not configured. Try a supported starter question or Custom Report.",
            )
        self.usage.llm_calls += 1
        started = time.perf_counter()
        result = None
        try:
            async with asyncio.timeout(self.base._settings.nlq_llm_timeout_seconds + 2):
                result = await complete_text(
                    settings=self.base._settings, system=system, user=prompt, max_tokens=max_tokens
                )
        except Exception as exc:
            self.usage.usage_complete = False
            raise BiProviderError(
                "provider_unavailable",
                "The AI service did not respond. Retry your question; the report is unchanged.",
            ) from exc
        finally:
            tokens = (result.prompt_tokens + result.completion_tokens) if result else 0
            self.usage.tokens += tokens
            active = active_llm(self.base._settings)
            pricing = (
                load_catalog(self.base._settings).model(active.provider, result.model)
                if result
                else None
            )
            estimate = (
                (
                    (
                        result.prompt_tokens * pricing.input_usd_per_1m
                        + result.completion_tokens * pricing.output_usd_per_1m
                    )
                    / 1000000
                )
                if result and pricing
                else tokens * 0.000002
            )
            self.base._app.add(
                LlmUsage(
                    user_id=self.base._user.id,
                    question="AskBI bounded completion",
                    model_name=(result.model if result else active_llm(self.base._settings).model)[
                        :120
                    ],
                    execution_mode="LLM",
                    prompt_tokens=result.prompt_tokens if result else 0,
                    completion_tokens=result.completion_tokens if result else 0,
                    total_tokens=tokens,
                    response_time_ms=int((time.perf_counter() - started) * 1000),
                    industry="automotive",
                    purpose="askbi",
                    estimated_cost_usd=estimate,
                )
            )
            await self.base._app.flush()
        if result.error or not result.content:
            self.usage.usage_complete = False
            raise BiProviderError(
                "provider_unavailable",
                "The AI service returned no usable answer. Retry; your report is unchanged.",
            )
        return result.content
