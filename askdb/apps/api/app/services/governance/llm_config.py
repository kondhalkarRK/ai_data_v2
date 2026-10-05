"""Admin-governed LLM configuration: provider, model, temperature and max tokens.

Providers and models come from ``config/llm_catalog.py`` (see ``llm_catalog``). The
choice lives in ``app_settings`` (key ``llm``). Each API process keeps a copy that the
chat routes re-read once per question, so every worker follows the admin's latest choice.
Without a saved choice the environment defaults apply.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ValidationError
from app.models.governance import AppSetting
from app.models.user import User
from app.services.governance.audit import AdminAction, record_admin_action
from app.services.governance.llm_catalog import LlmCatalog, load_catalog

logger = logging.getLogger(__name__)

SETTING_KEY = "llm"
DEFAULT_PROVIDER = "openai"
_PROVIDER_PREFIX = re.compile(r"^[a-z_]+\.")


@dataclass(frozen=True, slots=True)
class GovernedLlm:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    updated_at: str | None = None
    updated_by: str | None = None
    provider_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "provider": data["provider"],
            "providerLabel": self.provider_label or self.provider,
            "model": data["model"],
            "temperature": data["temperature"],
            "maxTokens": data["max_tokens"],
            "updatedAt": data["updated_at"],
            "updatedBy": data["updated_by"],
        }


_ACTIVE: GovernedLlm | None = None


def _label(catalog: LlmCatalog, provider_id: str) -> str:
    provider = catalog.provider(provider_id)
    return provider.label if provider else provider_id


def default_llm(settings: Settings) -> GovernedLlm:
    catalog = load_catalog(settings)
    model = settings.llm_default_model
    provider = next(
        (p.id for p in catalog.providers if any(m.id == model for m in p.models)),
        DEFAULT_PROVIDER,
    )
    return GovernedLlm(
        provider=provider,
        model=model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_completion_tokens,
        provider_label=_label(catalog, provider),
    )


def active_llm(settings: Settings) -> GovernedLlm:
    return _ACTIVE or default_llm(settings)


def set_active_llm(value: GovernedLlm | None) -> None:
    global _ACTIVE
    _ACTIVE = value


def _secret(value: Any) -> str:
    return value.get_secret_value().strip() if value is not None else ""


def _connection(settings: Settings, provider_id: str) -> str:
    provider = load_catalog(settings).provider(provider_id)
    if provider is not None:
        return provider.connection
    # A saved or default provider missing from the catalog still reaches the gateway.
    return "gateway" if provider_id == DEFAULT_PROVIDER else ""


def endpoint(settings: Settings, provider: str) -> tuple[str, dict[str, str]] | None:
    """Base URL and auth headers for a provider, or ``None`` when it is not configured."""
    connection = _connection(settings, provider)
    if connection == "gateway":
        key = _secret(settings.llm_api_key)
        return (settings.llm_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if connection == "anthropic":
        key = _secret(settings.anthropic_api_key)
        return (settings.anthropic_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if connection == "gemini":
        key = _secret(settings.gemini_api_key)
        return (settings.gemini_base_url, {"Authorization": f"Bearer {key}"}) if key else None
    if connection == "azure_openai":
        key = _secret(settings.azure_openai_api_key)
        url = settings.azure_openai_base_url.strip()
        return (url, {"api-key": key}) if key and url else None
    if connection == "ollama":
        url = settings.ollama_base_url.strip()
        return (url, {"Authorization": "Bearer ollama"}) if url else None
    if connection == "openai_compatible":
        entry = load_catalog(settings).provider(provider)
        if entry is None or not entry.base_url:
            return None
        key = os.environ.get(entry.api_key_env, "").strip() if entry.api_key_env else ""
        return (entry.base_url, {"Authorization": f"Bearer {key}"}) if key else None
    return None


def _bare(model_id: str) -> str:
    return _PROVIDER_PREFIX.sub("", model_id.strip().casefold(), count=1)


def _priced_match(catalog: LlmCatalog, model_id: str) -> dict[str, Any] | None:
    """Catalog entry for a model saved without (or with a different) provider prefix."""
    wanted = _bare(model_id)
    for provider in catalog.providers:
        for model in provider.models:
            if _bare(model.id) == wanted:
                return model.to_dict()
    return None


def llm_settings_payload(settings: Settings) -> dict[str, Any]:
    """Current choice, every catalog provider with its models, and pricing assumptions."""
    catalog = load_catalog(settings)
    current = active_llm(settings)
    providers = []
    for provider in catalog.providers:
        models = [model.to_dict() for model in provider.models]
        if provider.id == current.provider and all(m["id"] != current.model for m in models):
            match = _priced_match(catalog, current.model) or {}
            models.insert(
                0,
                {
                    "id": current.model,
                    "label": match.get("label") or current.model,
                    "tier": match.get("tier") or "",
                    "inputUsdPer1m": match.get("inputUsdPer1m"),
                    "outputUsdPer1m": match.get("outputUsdPer1m"),
                },
            )
        providers.append(
            {
                "id": provider.id,
                "label": provider.label,
                "configured": endpoint(settings, provider.id) is not None,
                "models": models,
            }
        )
    return {
        "current": current.to_dict(),
        "providers": providers,
        "pricing": {
            "inputTokensPerQuestion": catalog.input_tokens_per_question,
            "outputTokensPerQuestion": catalog.output_tokens_per_question,
            "monthlyBudgetUsd": settings.llm_monthly_budget_usd,
            "source": "config/llm_catalog.py",
        },
    }


def _from_row(settings: Settings, row: AppSetting) -> GovernedLlm:
    base = default_llm(settings)
    catalog = load_catalog(settings)
    value = row.value or {}
    provider = str(value.get("provider") or base.provider)
    if catalog.providers and catalog.provider(provider) is None:
        provider = base.provider
    return GovernedLlm(
        provider=provider,
        model=str(value.get("model") or base.model),
        temperature=float(value.get("temperature", base.temperature)),
        max_tokens=int(value.get("max_tokens", base.max_tokens)),
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        updated_by=value.get("updated_by"),
        provider_label=_label(catalog, provider),
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
    catalog = load_catalog(settings)
    entry = catalog.provider(provider)
    if entry is None:
        raise ValidationError(f"Unknown provider '{provider}'. Add it to config/llm_catalog.py.")
    if endpoint(settings, provider) is None:
        raise ValidationError(
            f"{entry.label} is not configured on the server. "
            "Add its API key / endpoint to the API environment first."
        )
    model = model.strip()
    if not model or len(model) > 120:
        raise ValidationError("Choose a model name (up to 120 characters).")

    before = await sync_llm_config(session, settings)
    known = {m.id for m in entry.models}
    if known and model not in known and not (provider == before.provider and model == before.model):
        raise ValidationError(f"'{model}' is not a {entry.label} model in config/llm_catalog.py.")
    after = GovernedLlm(
        provider=provider,
        model=model,
        temperature=round(float(temperature), 2),
        max_tokens=int(max_tokens),
        updated_at=datetime.now(UTC).isoformat(),
        updated_by=actor.username,
        provider_label=entry.label,
    )

    changes: list[tuple[str, str]] = []
    if before.provider != after.provider:
        changes.append(
            (
                AdminAction.CHANGED_LLM_PROVIDER,
                f"{before.provider_label or before.provider} → {after.provider_label}",
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
