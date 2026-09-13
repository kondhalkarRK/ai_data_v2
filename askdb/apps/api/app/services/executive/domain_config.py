"""Domain configuration for Executive Intelligence.

Industry is admin/session-selected — never inferred from data patterns.
KPI ids here are preferences; the semantic layer + live KPI engine decide
what is actually rendered.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Industry

# Extensible registry — add retail/banking/etc. later without rewriting UI.
DOMAIN_CONFIG: dict[str, dict[str, Any]] = {
    "automotive": {
        "title": "Automotive Intelligence",
        "tagline": "Your business, explained by AI",
        "primaryKpis": [
            "revenue",
            "units_sold",
            "avg_order_value",
            "rev_per_unit",
            "total_orders",
            "top_model",
        ],
        "secondaryKpis": ["active_regions", "top_make"],
        "insightCategories": ["risk", "opportunity", "insight", "recommendation"],
        "suggestedQuestionSeeds": [
            {"id": "models_revenue", "text": "Which vehicle models are driving revenue growth?", "requires": ["revenue", "model"]},
            {"id": "dealer_target", "text": "Which dealers are below target?", "requires": ["dealer"]},
            {"id": "inventory_aging", "text": "Where is inventory aging?", "requires": ["inventory"]},
            {"id": "sales_decline", "text": "Why did vehicle sales change this period?", "requires": ["units_sold"]},
            {"id": "top_models", "text": "Which models have the highest unit volume?", "requires": ["units_sold", "model"]},
        ],
        "glossaryHints": ["revenue", "units", "dealer", "model", "sales"],
        "healthScoreWeights": {
            "revenue": 0.35,
            "units_sold": 0.25,
            "avg_order_value": 0.20,
            "total_orders": 0.20,
        },
        "whatIfPresets": [
            {"id": "price_up_5", "label": "Vehicle price +5%", "metric": "revenue", "changeValue": 5, "direction": "up"},
            {"id": "units_up_3", "label": "Units sold +3%", "metric": "units_sold", "changeValue": 3, "direction": "up"},
            {"id": "aov_up_4", "label": "Average order value +4%", "metric": "avg_order_value", "changeValue": 4, "direction": "up"},
        ],
        "chartMetrics": ["revenue", "units_sold"],
        "dqTables": ["fact_sales"],
        "exploreFocus": ["revenue", "units_sold", "fact_sales"],
    },
    "insurance": {
        "title": "Insurance Intelligence",
        "tagline": "Your business, explained by AI",
        "primaryKpis": [
            "written_premium",
            "earned_premium",
            "loss_ratio",
            "renewal_rate",
            "claim_count",
            "approval_rate",
        ],
        "secondaryKpis": ["claims_incurred", "claims_paid", "average_severity"],
        "insightCategories": ["risk", "opportunity", "insight", "recommendation"],
        "suggestedQuestionSeeds": [
            {"id": "claims_ratio", "text": "Why did claims ratio change this period?", "requires": ["loss_ratio"]},
            {"id": "loss_segment", "text": "Which policy segment has the highest loss ratio?", "requires": ["loss_ratio", "lob"]},
            {"id": "premium_growth", "text": "What is driving premium growth?", "requires": ["written_premium"]},
            {"id": "renewal", "text": "How is renewal rate trending?", "requires": ["renewal_rate"]},
            {"id": "claims_freq", "text": "Which regions have the highest claims frequency?", "requires": ["claim_count", "region"]},
        ],
        "glossaryHints": ["premium", "claims", "loss ratio", "renewal", "policy"],
        "healthScoreWeights": {
            "written_premium": 0.30,
            "renewal_rate": 0.25,
            "loss_ratio": 0.25,
            "approval_rate": 0.20,
        },
        "whatIfPresets": [
            {"id": "renewal_up_5", "label": "Renewal rate +5%", "metric": "renewal_rate", "changeValue": 5, "direction": "up"},
            {"id": "premium_up_4", "label": "Average premium +4%", "metric": "written_premium", "changeValue": 4, "direction": "up"},
            {"id": "claims_up_3", "label": "Claims count +3%", "metric": "claim_count", "changeValue": 3, "direction": "up"},
        ],
        "chartMetrics": ["written_premium", "claims_incurred", "loss_ratio"],
        "dqTables": ["fact_claims", "fact_policy_monthly"],
        "exploreFocus": ["written_premium", "loss_ratio", "fact_claims"],
    },
}


def get_domain_config(industry: Industry | str) -> dict[str, Any]:
    key = industry.value if isinstance(industry, Industry) else str(industry)
    cfg = DOMAIN_CONFIG.get(key)
    if cfg is None:
        # Extensibility: unknown industries fall back to an empty shell, never fake KPIs.
        return {
            "title": f"{key.title()} Intelligence",
            "tagline": "Your business, explained by AI",
            "primaryKpis": [],
            "secondaryKpis": [],
            "insightCategories": ["risk", "opportunity", "insight", "recommendation"],
            "suggestedQuestionSeeds": [],
            "glossaryHints": [],
            "healthScoreWeights": {},
            "whatIfPresets": [],
            "chartMetrics": [],
            "dqTables": [],
            "exploreFocus": [],
        }
    return cfg
