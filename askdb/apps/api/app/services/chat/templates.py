"""Deterministic NLQ templates so chat works without an LLM key."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Industry
from app.services.chat.question_understanding import (
    QuestionPlan,
    understand_question,
)


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
        else [
            "revenue by month",
            "top salesperson",
            "top dealer by revenue",
            "top selling sedan",
            "electric share",
        ]
    )
    return [
        hit
        for question in examples
        if (hit := resolve_template(industry, question)) is not None
    ]


def resolve_template(industry: Industry, question: str) -> TemplateHit | None:
    q = question.strip()
    if not q:
        return None

    plan = understand_question(industry, q)
    if plan.is_ambiguous:
        return None

    if industry is Industry.INSURANCE:
        return _insurance_templates(q.lower())

    if industry is Industry.AUTOMOTIVE:
        hit = _automotive_from_plan(plan)
        if hit is not None:
            return hit
        return _automotive_fallback(q.lower())

    return None


def _order_metric(metric: str) -> tuple[str, str]:
    """Return (select_extra_order_expr, order_by_position)."""
    if metric == "revenue":
        return "SUM(f.total_sales) AS revenue, SUM(f.order_qty) AS units_sold", "3"
    return "SUM(f.order_qty) AS units_sold, SUM(f.total_sales) AS revenue", "3"


def _car_type_where(plan: QuestionPlan) -> str:
    clauses: list[str] = []
    for filt in plan.filters:
        if "car_type" in filt.column:
            clauses.append(f"c.car_type = '{filt.value}'")
        if "engine_type" in filt.column:
            clauses.append(f"c.engine_type = '{filt.value}'")
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)


def _automotive_from_plan(plan: QuestionPlan) -> TemplateHit | None:
    limit = plan.limit or 10
    metric = plan.metric if plan.metric != "unknown" else "units"
    select_metrics, order_pos = _order_metric(metric)

    if plan.entity == "salesperson":
        return TemplateHit(
            title="Top salespeople by " + ("revenue" if metric == "revenue" else "units"),
            glossary_matches=3,
            sql=f"""
SELECT (s.first_name || ' ' || s.last_name) AS salesperson_name,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_salesman s ON s.sales_person_id = f.sales_person_id
GROUP BY 1
ORDER BY {order_pos} DESC
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "dealer":
        return TemplateHit(
            title="Top dealers by " + ("revenue" if metric == "revenue" else "units"),
            glossary_matches=2,
            sql=f"""
SELECT d.dealer_name, d.dealer_grade, d.city,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
GROUP BY 1, 2, 3
ORDER BY {order_pos} DESC
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "region" and plan.intent == "ranking":
        return TemplateHit(
            title="Top regions by units",
            glossary_matches=2,
            sql=f"""
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       SUM(f.order_qty) AS units_sold,
       SUM(f.total_sales) AS revenue
FROM automotive.fact_sales f
LEFT JOIN automotive.dim_region r ON r.region_id = f.region_id
GROUP BY 1
ORDER BY 2 DESC
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "vehicle" and plan.intent in {"ranking", "aggregation"}:
        if any("group by region" in n.lower() for n in plan.notes):
            return TemplateHit(
                title="Top cars by region",
                glossary_matches=2,
                sql=f"""
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       c.model, c.make, c.car_type,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
LEFT JOIN automotive.dim_region r ON r.region_id = f.region_id
GROUP BY 1, 2, 3, 4
ORDER BY {order_pos} DESC
LIMIT {limit}
""".strip(),
            )
        where = _car_type_where(plan)
        filter_label = ", ".join(f.label for f in plan.filters) or "all body styles"
        metric_label = "revenue" if metric == "revenue" else "units"
        return TemplateHit(
            title=f"Top vehicles by {metric_label} ({filter_label})",
            glossary_matches=2 + len(plan.filters),
            sql=f"""
SELECT c.model, c.make, c.car_type,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
{where}
GROUP BY 1, 2, 3
ORDER BY {order_pos} DESC
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "metric_only" and plan.metric == "revenue":
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

    return None


def _automotive_fallback(q: str) -> TemplateHit | None:
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
LIMIT 20
""".strip(),
        )
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
    return None


def _insurance_templates(q: str) -> TemplateHit | None:
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
    return None
