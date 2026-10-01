"""Admin-governed LLM configuration: provider, model, temperature and max tokens.

The choice lives in ``app_settings`` (key ``llm``). Each API process keeps a copy that the
chat routes re-read once per question, so every worker follows the admin's latest choice.
Without a saved choice the environment defaults apply.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.models.governance import AppSetting
from app.models.user import User
from app.services.governance.audit import AdminAction, record_admin_action

logger = logging.getLogger(__name__)

SETTING_KEY = "llm"


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    id: str
    label: str
    suggested_models: tuple[str, ...]


PROVIDERS: dict[str, ProviderInfo] = {
    "openai": ProviderInfo("openai", "OpenAI", ("gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini")),
    "claude": ProviderInfo("claude", "Claude", ("claude-sonnet-4-5", "claude-haiku-4-5")),
    "gemini": ProviderInfo("gemini", "Gemini", ("gemini-2.5-pro", "gemini-2.5-flash")),
    "azure_openai": ProviderInfo("azure_openai", "Azure OpenAI", ("gpt-4.1", "gpt-4o-mini")),
    "ollama": ProviderInfo("ollama", "Ollama", ("llama3.1", "qwen2.5-coder")),
}


@dataclass(frozen=True, slots=True)
class GovernedLlm:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    updated_at: str | None = None
    updated_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "provider": data["provider"],
            "providerLabel": PROVIDERS[self.provider].label,
            "model": data["model"],
            "temperature": data["temperature"],
            "maxTokens": data["max_tokens"],
            "updatedAt": data["updated_at"],
            "updatedBy": data["updated_by"],
        }


_ACTIVE: GovernedLlm | None = None


def default_llm(settings: Settings) -> GovernedLlm:
    return GovernedLlm(
        provider="openai",
        model=settings.llm_default_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_completion_tokens,
    )


def active_llm(settings: Settings) -> GovernedLlm:
    return _ACTIVE or default_llm(settings)


def set_active_llm(value: GovernedLlm | None) -> None:
    global _ACTIVE
    _ACTIVE = value


def _secret(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def endpoint(settings: Settings, provider: str) -> tuple[str, dict[str, str]] | None:
    """Base URL and auth headers for a provider, or ``None`` when it is not configured."""
    if provider == "openai":
        key = _secret(settings.llm_api_key)
        return (settings.llm_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if provider == "claude":
        key = _secret(settings.anthropic_api_key)
        return (settings.anthropic_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if provider == "gemini":
        key = _secret(settings.gemini_api_key)
        return (settings.gemini_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if provider == "azure_openai":
        key = _secret(settings.azure_openai_api_key)
        url = settings.azure_openai_base_url.strip()
        return (url, {"api-key": key}) if key and url else None
    if provider == "ollama":
        url = settings.ollama_base_url.strip()
        return (url, {"Authorization": "Bearer ollama"}) if url else None
    return None


def provider_options(settings: Settings) -> list[dict[str, Any]]:
    current = active_llm(settings)
    options = []
    for info in PROVIDERS.values():
        models = list(info.suggested_models)
        if info.id == "openai":
            for model in (settings.llm_default_model, settings.llm_fallback_model.strip()):
                if model and model not in models:
                    models.insert(0, model)
        if info.id == current.provider and current.model not in models:
            models.insert(0, current.model)
        options.append(
            {
                "id": info.id,
                "label": info.label,
                "configured": endpoint(settings, info.id) is not None,
                "models": models,
            }
        )
    return options


def _from_row(settings: Settings, row: AppSetting) -> GovernedLlm:
    base = default_llm(settings)
    value = row.value or {}
    provider = str(value.get("provider") or base.provider)
    if provider not in PROVIDERS:
        provider = base.provider
    return GovernedLlm(
        provider=provider,
        model=str(value.get("model") or base.model),
        temperature=float(value.get("temperature", base.temperature)),
        max_tokens=int(value.get("max_tokens", base.max_tokens)),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        updated_by=value.get("updated_by"),
    )


async def sync_llm_config(session: AsyncSession, settings: Settings) -> GovernedLlm:
    """Refresh this process's copy from ``app_settings``; keep the old copy if unreadable."""
    try:
        row = await session.get(AppSetting, SETTING_KEY)
    except Exception:
        logger.debug("llm governance: app_settings unavailable", exc_info=True)
        return active_llm(settings)
    set_active_llm(_from_row(settings, row) if row is not None else None)
    return active_llm(settings)


async def update_llm_config(
    session: AsyncSession,
    settings: Settings,
    actor: User,
    *,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> GovernedLlm:
    if provider not in PROVIDERS:
        raise ValidationError(f"Unknown provider '{provider}'.")
    if endpoint(settings, provider) is None:
        raise ValidationError(
            f"{PROVIDERS[provider].label} is not configured on the server. "
            "Add its API key / endpoint to the API environment first."
        )
    model = model.strip()
    if not model or len(model) > 120:
        raise ValidationError("Choose a model name (up to 120 characters).")

    before = await sync_llm_config(session, settings)
    after = GovernedLlm(
        provider=provider,
        model=model,
        temperature=round(float(temperature), 2),
        max_tokens=int(max_tokens),
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=actor.username,
    )

    changes: list[tuple[str, str]] = []
    if before.provider != after.provider:
        changes.append(
            (
                AdminAction.CHANGED_LLM_PROVIDER,
                f"{PROVIDERS[before.provider].label} → {PROVIDERS[after.provider].label}",
            )
        )
    if before.model != after.model:
        changes.append((AdminAction.CHANGED_LLM_MODEL, f"{before.model} → {after.model}"))
    if before.temperature != after.temperature:
        changes.append(
            (AdminAction.CHANGED_TEMPERATURE, f"{before.temperature} → {after.temperature}")
        )
    if before.max_tokens != after.max_tokens:
        changes.append(
            (AdminAction.CHANGED_MAX_TOKENS, f"{before.max_tokens} → {after.max_tokens}")
        )
    if not changes:
        return before

    value = {
        "provider": after.provider,
        "model": after.model,
        "temperature": after.temperature,
        "max_tokens": after.max_tokens,
        "updated_by": after.updated_by,
    }
    row = await session.get(AppSetting, SETTING_KEY)
    if row is None:
        session.add(AppSetting(key=SETTING_KEY, value=value, updated_by=actor.id))
    else:
        row.value = value
        row.updated_by = actor.id
        row.updated_at = datetime.now(UTC)
    for action, details in changes:
        await record_admin_action(session, actor.id, action, details)
    await session.flush()
    set_active_llm(after)
    return after
