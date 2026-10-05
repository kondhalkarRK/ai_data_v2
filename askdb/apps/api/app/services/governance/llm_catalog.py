"""Providers, models and indicative pricing loaded from ``config/llm_catalog.py``.

The catalog file is the only place providers and models are defined. It is re-read when
its modification time changes, so a new provider appears in LLM Settings without a
restart.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.config import REPO_ROOT, Settings

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = REPO_ROOT.parent / "config" / "llm_catalog.py"
DEFAULT_INPUT_TOKENS = 2_000
DEFAULT_OUTPUT_TOKENS = 500


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    label: str
    tier: str
    input_usd_per_1m: float
    output_usd_per_1m: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tier": self.tier,
            "inputUsdPer1m": self.input_usd_per_1m,
            "outputUsdPer1m": self.output_usd_per_1m,
        }


@dataclass(frozen=True, slots=True)
class CatalogProvider:
    id: str
    label: str
    connection: str
    models: tuple[CatalogModel, ...]
    base_url: str = ""
    api_key_env: str = ""


@dataclass(frozen=True, slots=True)
class LlmCatalog:
    providers: tuple[CatalogProvider, ...] = ()
    input_tokens_per_question: int = DEFAULT_INPUT_TOKENS
    output_tokens_per_question: int = DEFAULT_OUTPUT_TOKENS
    source: str = ""
    by_id: dict[str, CatalogProvider] = field(default_factory=dict)

    def provider(self, provider_id: str) -> CatalogProvider | None:
        return self.by_id.get(provider_id)

    def model(self, provider_id: str, model_id: str) -> CatalogModel | None:
        provider = self.provider(provider_id)
        if provider is None:
            return None
        return next((m for m in provider.models if m.id == model_id), None)


_CACHE: tuple[str, float, LlmCatalog] | None = None


def catalog_path(settings: Settings) -> Path:
    configured = (settings.llm_catalog_path or "").strip()
    return Path(configured) if configured else DEFAULT_CATALOG_PATH


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("askdb_llm_catalog", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _price(item: dict[str, Any], key: str) -> float:
    value = item.get(key)
    if value is None:
        value = item.get("usd_per_1m", 0.0)
    return float(value or 0.0)


def build_catalog(module: Any, source: str = "") -> LlmCatalog:
    endpoints = [
        *getattr(module, "CG_ENDPOINTS", []),
        *getattr(module, "PROVIDER_ENDPOINTS", []),
    ]
    providers: list[CatalogProvider] = []
    for raw in getattr(module, "LLM_PROVIDERS", []):
        families = {str(f) for f in raw.get("families") or [raw.get("id")]}
        models = tuple(
            CatalogModel(
                id=str(item["id"]),
                label=str(item.get("label") or item["id"]),
                tier=str(item.get("tier") or ""),
                input_usd_per_1m=_price(item, "usd_per_1m_input"),
                output_usd_per_1m=_price(item, "usd_per_1m_output"),
            )
            for item in endpoints
            if str(item.get("family")) in families
        )
        providers.append(
            CatalogProvider(
                id=str(raw["id"]),
                label=str(raw.get("label") or raw["id"]),
                connection=str(raw.get("connection") or "openai_compatible"),
                models=models,
                base_url=str(raw.get("base_url") or ""),
                api_key_env=str(raw.get("api_key_env") or ""),
            )
        )
    return LlmCatalog(
        providers=tuple(providers),
        input_tokens_per_question=int(
            getattr(module, "AVG_INPUT_TOKENS_PER_QUESTION", DEFAULT_INPUT_TOKENS)
        ),
        output_tokens_per_question=int(
            getattr(module, "AVG_OUTPUT_TOKENS_PER_QUESTION", DEFAULT_OUTPUT_TOKENS)
        ),
        source=source,
        by_id={provider.id: provider for provider in providers},
    )


def load_catalog(settings: Settings) -> LlmCatalog:
    """The current catalog; an empty one when the file is missing or invalid."""
    global _CACHE
    path = catalog_path(settings)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        logger.warning("LLM catalog not found at %s", path)
        return LlmCatalog(source=str(path))
    if _CACHE is not None and _CACHE[0] == str(path) and _CACHE[1] == mtime:
        return _CACHE[2]
    try:
        catalog = build_catalog(_load_module(path), source=str(path))
    except Exception:
        logger.warning("LLM catalog at %s could not be loaded", path, exc_info=True)
        return _CACHE[2] if _CACHE is not None else LlmCatalog(source=str(path))
    _CACHE = (str(path), mtime, catalog)
    return catalog
