"""Deterministic NLQ templates so chat works without an LLM key."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Industry


@dataclass(frozen=True, slots=True)
class TemplateHit:
    sql: str
    title: str
    glossary_matches: int
    path: str = "template"


def list_templates(industry: Industry) -> list[TemplateHit]:
    """Return every governed template available for an industry."""
    examples = (
        ["loss ratio", "claim count", "written premium", "top region"]
        if industry is Industry.INSURANCE
        else ["revenue", "top model", "electric share", "dealer"]
    )
    return [
        hit
        for question in examples
        if (hit := resolve_template(industry, question)) is not None
    ]


def resolve_template(industry: Industry, question: str) -> TemplateHit | None:
    q = question.strip().lower()
    if not q:
        return None

    if industry is Industry.INSURANCE:
        if re.search(r"loss\s*ratio", q):
            return TemplateHit(
                title="Loss ratio by month",
                glossary_matches=2,
                sql="""
SELECT date_trunc('month', c.reported_date)::date AS month,
       SUM(c.incurred_amount) AS claims_incurred,
       (
         SELECT SUM(pm.earned_premium)
         FROM insurance.fact_policy_monthly pm
         WHERE date_trunc('month', pm.accounting_month)
             = date_trunc('month', c.reported_date)
       ) AS earned_premium,
       SUM(c.incurred_amount) / NULLIF((
         SELECT SUM(pm.earned_premium)
         FROM insurance.fact_policy_monthly pm
         WHERE date_trunc('month', pm.accounting_month)
             = date_trunc('month', c.reported_date)
       ), 0) AS loss_ratio
FROM insurance.fact_claims c
WHERE c.reported_date >= DATE '2024-01-01'
GROUP BY 1
ORDER BY 1
LIMIT 24
""".strip(),
            )
        if re.search(r"claim.*(count|volume)|how many claims", q):
            return TemplateHit(
                title="Claim count by status",
                glossary_matches=2,
                sql="""
SELECT claim_status, COUNT(*) AS claim_count
FROM insurance.fact_claims
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20
""".strip(),
            )
        if re.search(r"written\s*premium|gwp|earned\s*premium", q):
            return TemplateHit(
                title="Premium by month",
                glossary_matches=2,
                sql="""
SELECT accounting_month,
       SUM(written_premium) AS written_premium,
       SUM(earned_premium) AS earned_premium
FROM insurance.fact_policy_monthly
WHERE accounting_month >= DATE '2024-01-01'
GROUP BY 1
ORDER BY 1
LIMIT 36
""".strip(),
            )
        if re.search(r"top\s+region|by\s+region", q):
            return TemplateHit(
                title="Incurred by region",
                glossary_matches=1,
                sql="""
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       SUM(c.incurred_amount) AS claims_incurred
FROM insurance.fact_claims c
LEFT JOIN insurance.dim_region r ON r.region_id = c.region_id
GROUP BY 1
ORDER BY 2 DESC
LIMIT 15
""".strip(),
            )

    if industry is Industry.AUTOMOTIVE:
        if re.search(r"revenue|sales\s+value|total\s+sales", q):
            return TemplateHit(
                title="Revenue by month",
                glossary_matches=2,
                sql="""
SELECT date_trunc('month', sales_date)::date AS month,
       SUM(total_sales) AS revenue,
       SUM(order_qty) AS units_sold
FROM automotive.fact_sales
WHERE sales_date >= DATE '2024-01-01'
GROUP BY 1
ORDER BY 1
LIMIT 36
""".strip(),
            )
        if re.search(r"top\s+model|best\s+selling|units\s+sold", q):
            return TemplateHit(
                title="Top models by units",
                glossary_matches=2,
                sql="""
SELECT c.model, c.make, SUM(f.order_qty) AS units_sold, SUM(f.total_sales) AS revenue
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 15
""".strip(),
            )
        if re.search(r"electric|ev\s+share|engine_type", q):
            return TemplateHit(
                title="EV share by year",
                glossary_matches=1,
                sql="""
SELECT EXTRACT(YEAR FROM f.sales_date)::int AS year,
       SUM(f.order_qty) FILTER (WHERE c.engine_type = 'Electric')::float
         / NULLIF(SUM(f.order_qty), 0) AS ev_share
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
GROUP BY 1
ORDER BY 1
""".strip(),
            )
        if re.search(r"dealer", q):
            return TemplateHit(
                title="Dealer performance",
                glossary_matches=1,
                sql="""
SELECT d.dealer_name, d.dealer_grade,
       SUM(f.order_qty) AS units_sold,
       SUM(f.total_sales) AS revenue
FROM automotive.fact_sales f
JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
GROUP BY 1, 2
ORDER BY 4 DESC
LIMIT 20
""".strip(),
            )

    return None
