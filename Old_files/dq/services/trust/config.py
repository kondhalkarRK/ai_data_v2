"""Trust scoring weights and per-dataset SLA expectations.

Expectations are admin-configured — never inferred from silent heuristics.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Industry

# Expandable Trust Score factors (Section 1).
TRUST_SCORE_WEIGHTS: dict[str, float] = {
    "freshness": 0.18,
    "completeness": 0.18,
    "uniqueness": 0.14,
    "validity": 0.14,
    "consistency": 0.12,
    "schema_stability": 0.12,
    "dq_rule_success": 0.12,
}

# Expected refresh SLA in hours per physical-ish table key (logical name).
# Delay is measured against these baselines — not an implicit clock.
DATASET_SLA_HOURS: dict[str, dict[str, float]] = {
    "automotive": {
        "fact_sales": 24,
        "dim_carline": 168,
        "dim_dealer": 168,
        "dim_region": 168,
    },
    "insurance": {
        "fact_claims": 12,
        "fact_policy_monthly": 24,
        "dim_product": 168,
        "dim_region": 168,
        "dim_customer": 168,
    },
}

# Default notification architecture (channels wired incrementally).
DEFAULT_NOTIFICATION_RULES: list[dict[str, Any]] = [
    {
        "id": "high_severity_webhook",
        "name": "High severity incidents",
        "minSeverity": "high",
        "channel": "webhook",
        "target": "",
        "enabled": False,
        "note": "Configure a webhook URL to enable push alerts. Slack/email/Teams land incrementally.",
    },
    {
        "id": "critical_email",
        "name": "Critical email digest",
        "minSeverity": "critical",
        "channel": "email",
        "target": "",
        "enabled": False,
        "note": "Email delivery is not connected yet — rule is stored for future activation.",
    },
]


def sla_hours_for(industry: Industry | str, table_name: str) -> float | None:
    key = industry.value if isinstance(industry, Industry) else str(industry)
    return DATASET_SLA_HOURS.get(key, {}).get(table_name)


def trust_weights() -> dict[str, float]:
    return dict(TRUST_SCORE_WEIGHTS)
