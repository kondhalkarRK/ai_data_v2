from __future__ import annotations

from types import SimpleNamespace

from app.core.config import get_settings
from app.services.governance.llm_catalog import DEFAULT_CATALOG_PATH, build_catalog, load_catalog


def test_repository_catalog_lists_every_provider() -> None:
    assert DEFAULT_CATALOG_PATH.exists()
    catalog = load_catalog(get_settings())
    ids = {provider.id for provider in catalog.providers}
    assert {"openai", "claude", "gemini", "azure_openai", "ollama"} <= ids
    mini = catalog.model("openai", "openai.gpt-5-mini")
    assert mini is not None
    assert mini.input_usd_per_1m < mini.output_usd_per_1m


def test_new_provider_needs_only_catalog_entries() -> None:
    module = SimpleNamespace(
        CG_ENDPOINTS=[],
        PROVIDER_ENDPOINTS=[
            {"id": "mistral-large", "family": "mistral", "tier": "high", "label": "Mistral Large",
             "usd_per_1m_input": 2.0, "usd_per_1m_output": 6.0},
        ],
        LLM_PROVIDERS=[
            {"id": "mistral", "label": "Mistral", "families": ["mistral"],
             "connection": "openai_compatible", "base_url": "https://api.mistral.ai/v1",
             "api_key_env": "MISTRAL_API_KEY"},
        ],
        AVG_INPUT_TOKENS_PER_QUESTION=1000,
        AVG_OUTPUT_TOKENS_PER_QUESTION=250,
    )
    catalog = build_catalog(module)
    provider = catalog.provider("mistral")
    assert provider is not None
    assert provider.connection == "openai_compatible"
    assert [m.id for m in provider.models] == ["mistral-large"]
    assert catalog.input_tokens_per_question == 1000


def test_blended_price_is_used_when_split_is_missing() -> None:
    module = SimpleNamespace(
        CG_ENDPOINTS=[{"id": "x", "family": "gpt", "label": "X", "usd_per_1m": 3.0}],
        LLM_PROVIDERS=[
            {"id": "openai", "label": "OpenAI", "families": ["gpt"], "connection": "gateway"}
        ],
    )
    model = build_catalog(module).model("openai", "x")
    assert model is not None
    assert model.input_usd_per_1m == model.output_usd_per_1m == 3.0
