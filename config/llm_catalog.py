"""Capgemini Studio LLM catalog: exact route IDs, tiers, and indicative cost."""
from __future__ import annotations

from typing import Any

# Model IDs must match Capgemini Studio / gateway route names.
CG_ENDPOINTS: list[dict[str, Any]] = [
    {
        "id": "openai.gpt-5-nano",
        "family": "gpt",
        "tier": "small",
        "label": "GPT-5 nano",
        "usd_per_1m": 0.20,
    },
    {
        "id": "openai.gpt-3.5-turbo",
        "family": "gpt",
        "tier": "small",
        "label": "GPT-3.5 turbo",
        "usd_per_1m": 0.50,
    },
    {
        "id": "openai.gpt-5-mini",
        "family": "gpt",
        "tier": "medium",
        "label": "GPT-5 mini",
        "usd_per_1m": 0.80,
    },
    {
        "id": "openai.gpt-4o",
        "family": "gpt",
        "tier": "medium",
        "label": "GPT-4o",
        "usd_per_1m": 5.00,
    },
    {
        "id": "openai.gpt-5",
        "family": "gpt",
        "tier": "high",
        "label": "GPT-5",
        "usd_per_1m": 8.00,
    },
    {
        "id": "openai.gpt-5.1",
        "family": "gpt",
        "tier": "high",
        "label": "GPT-5.1",
        "usd_per_1m": 10.00,
    },
    {
        "id": "anthropic.claude-haiku-4-5-20251001-v1:0",
        "family": "claude",
        "tier": "small",
        "label": "Claude Haiku 4.5",
        "usd_per_1m": 1.00,
        "route": "bedrock",
    },
    {
        "id": "anthropic.claude-sonnet-5",
        "family": "claude",
        "tier": "medium",
        "label": "Claude Sonnet 5",
        "usd_per_1m": 6.00,
        "route": "bedrock",
    },
    {
        "id": "anthropic.claude-opus-5",
        "family": "claude",
        "tier": "high",
        "label": "Claude Opus 5",
        "usd_per_1m": 20.00,
        "route": "bedrock",
    },
]

# Default size mapping sent when the user picks only provider + size.
LLM_PROFILES: dict[tuple[str, str], dict[str, Any]] = {
    ("gpt", "small"): next(m for m in CG_ENDPOINTS if m["id"] == "openai.gpt-5-nano"),
    ("gpt", "medium"): next(m for m in CG_ENDPOINTS if m["id"] == "openai.gpt-5-mini"),
    ("gpt", "high"): next(m for m in CG_ENDPOINTS if m["id"] == "openai.gpt-5.1"),
    ("claude", "small"): next(
        m for m in CG_ENDPOINTS if m["id"] == "anthropic.claude-haiku-4-5-20251001-v1:0"
    ),
    ("claude", "medium"): next(
        m for m in CG_ENDPOINTS if m["id"] == "anthropic.claude-sonnet-5"
    ),
    ("claude", "high"): next(
        m for m in CG_ENDPOINTS if m["id"] == "anthropic.claude-opus-5"
    ),
}

DEFAULT_FAMILY = "gpt"
DEFAULT_TIER = "high"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MODEL_ID = "openai.gpt-5.1"


def get_endpoint(model_id: str | None) -> dict[str, Any] | None:
    if not model_id:
        return None
    for item in CG_ENDPOINTS:
        if item["id"] == model_id:
            return item
    return None


def get_profile(family: str, tier: str, model_id: str | None = None) -> dict[str, Any]:
    chosen = get_endpoint(model_id)
    if chosen:
        return {
            "label": f"{chosen['label']} ({chosen['tier']})",
            "model": chosen["id"],
            "usd_per_1m": chosen["usd_per_1m"],
            "family": chosen["family"],
            "tier": chosen["tier"],
        }
    key = (str(family or DEFAULT_FAMILY).lower(), str(tier or DEFAULT_TIER).lower())
    item = LLM_PROFILES.get(key, LLM_PROFILES[(DEFAULT_FAMILY, DEFAULT_TIER)])
    return {
        "label": f"{item['label']} ({item['tier']})",
        "model": item["id"],
        "usd_per_1m": item["usd_per_1m"],
        "family": item["family"],
        "tier": item["tier"],
    }


def models_for_family(family: str) -> list[dict[str, Any]]:
    fam = str(family or DEFAULT_FAMILY).lower()
    return [item for item in CG_ENDPOINTS if item["family"] == fam]


def tokens_per_dollar(usd_per_1m: float) -> int:
    if not usd_per_1m:
        return 0
    return int(round(1_000_000 / float(usd_per_1m)))


def estimate_usd(tokens: int, usd_per_1m: float) -> float:
    return float(tokens) / 1_000_000.0 * float(usd_per_1m)


# Indicative average tokens per Chat turn (prompt + completion).
TOKENS_PER_QUESTION_NO_NARRATION = 2_500
TOKENS_PER_QUESTION_WITH_NARRATION = 6_000


def questions_per_dollar(
    usd_per_1m: float,
    *,
    with_narration: bool = False,
) -> int:
    """Rough count of Chat questions $1 can buy at indicative Studio pricing."""
    tokens = tokens_per_dollar(usd_per_1m)
    per_q = (
        TOKENS_PER_QUESTION_WITH_NARRATION
        if with_narration
        else TOKENS_PER_QUESTION_NO_NARRATION
    )
    if not tokens or not per_q:
        return 0
    return max(int(tokens // per_q), 0)

