"""Deterministic NLQ templates so chat works without an LLM key."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Industry
from app.services.chat.question_understanding import (
    QuestionPlan,
    understand_question,
)
from app.services.chat.semantic_analytics import (
    SemanticCompileError,
    compile_analytical_query,
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
        hit for question in examples if (hit := resolve_template(industry, question)) is not None
    ]


def resolve_template(
    industry: Industry,
    question: str,
    *,
    plan: QuestionPlan | None = None,
    pack: object | None = None,
) -> TemplateHit | None:
    q = question.strip()
    if not q:
        return None

    plan = plan or understand_question(industry, q)
    if plan.is_ambiguous:
        return None

    # Rich plans must be compiled before narrow legacy templates get a chance to
    # collapse the grain (for example month + car type + colour -> month only).
    if plan.requires_semantic_compiler:
        try:
            compiled = compile_analytical_query(plan, pack)
        except SemanticCompileError:
            return None
        if compiled is not None:
            return TemplateHit(
                sql=compiled.sql,
                title=compiled.title,
                glossary_matches=max(2, len(plan.dimensions) + 1),
                path="semantic_compiler",
            )
        if pack is None:
            # Offline inventory/tests and deployments without a loaded pack retain
            # the existing governed templates. Runtime always supplies the pack.
            pass
        elif (
            plan.industry is Industry.AUTOMOTIVE
            and plan.entity == "vehicle"
            and any("group by region" in note.lower() for note in plan.notes)
        ):
            # Backward-compatible governed template; also keeps offline template
            # inventory/tests useful when no pack object is available.
            pass
        else:
            # Never silently route an advanced plan to a less expressive fallback.
            return None

    if industry is Industry.AUTOMOTIVE:
        hit = _automotive_from_plan(plan)
        if hit is not None:
            return hit
        return _automotive_fallback(q.lower())

    return _insurance_from_plan(plan) or _insurance_templates(q.lower())


def _order_metric(metric: str) -> tuple[str, str]:
    """Return (select metrics, primary metric alias)."""
    if metric == "revenue":
        return "SUM(f.total_sales) AS revenue, SUM(f.order_qty) AS units_sold", "revenue"
    if metric == "orders":
        return "COUNT(DISTINCT f.order_id) AS orders, SUM(f.order_qty) AS units_sold", "orders"
    return "SUM(f.order_qty) AS units_sold, SUM(f.total_sales) AS revenue", "units_sold"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _automotive_filter_parts(
    plan: QuestionPlan,
    *,
    base_aliases: set[str],
) -> tuple[list[str], str]:
    joins: list[str] = []
    clauses: list[str] = []
    aliases = set(base_aliases)
    alias_map = {
        "automotive.dim_carline": (
            "c",
            "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id",
        ),
        "automotive.dim_color": (
            "co",
            "JOIN automotive.dim_color co ON co.colour_id = f.colour_id",
        ),
        "automotive.dim_region": ("r", "JOIN automotive.dim_region r ON r.region_id = f.region_id"),
        "automotive.dim_dealer": ("d", "JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id"),
    }
    for filt in plan.filters:
        table, _, column = filt.column.rpartition(".")
        mapping = alias_map.get(table)
        if mapping is None:
            continue
        alias, join = mapping
        if alias not in aliases:
            joins.append(join)
            aliases.add(alias)
        clauses.append(f"{alias}.{column} {filt.operator} {_sql_literal(filt.value)}")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return joins, where


def _automotive_from_plan(plan: QuestionPlan) -> TemplateHit | None:
    limit = plan.limit or 10
    metric = plan.metric if plan.metric != "unknown" else "units"
    select_metrics, order_alias = _order_metric(metric)
    direction = plan.order_direction.upper()

    if plan.entity == "salesperson":
        joins, where = _automotive_filter_parts(plan, base_aliases={"s"})
        extra_joins = "\n".join(joins)
        return TemplateHit(
            title=("Lowest" if direction == "ASC" else "Top")
            + " salespeople by "
            + ("revenue" if metric == "revenue" else "units"),
            glossary_matches=3,
            sql=f"""
SELECT (s.first_name || ' ' || s.last_name) AS salesperson_name,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_salesman s ON s.sales_person_id = f.sales_person_id
{extra_joins}
{where}
GROUP BY 1
ORDER BY {order_alias} {direction}
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "dealer":
        joins, where = _automotive_filter_parts(plan, base_aliases={"d"})
        extra_joins = "\n".join(joins)
        return TemplateHit(
            title=("Lowest" if direction == "ASC" else "Top")
            + " dealers by "
            + ("revenue" if metric == "revenue" else "units"),
            glossary_matches=2,
            sql=f"""
SELECT d.dealer_name, d.dealer_grade, d.city,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id
{extra_joins}
{where}
GROUP BY 1, 2, 3
ORDER BY {order_alias} {direction}
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "region" and plan.intent in {"ranking", "aggregation"}:
        joins, where = _automotive_filter_parts(plan, base_aliases={"r"})
        extra_joins = "\n".join(joins)
        order_alias = "revenue" if metric == "revenue" else "units_sold"
        return TemplateHit(
            title=("Lowest" if direction == "ASC" else "Top") + f" regions by {metric}",
            glossary_matches=2,
            sql=f"""
SELECT COALESCE(r.region_name, 'Unknown') AS region_name,
       SUM(f.order_qty) AS units_sold,
       SUM(f.total_sales) AS revenue
FROM automotive.fact_sales f
LEFT JOIN automotive.dim_region r ON r.region_id = f.region_id
{extra_joins}
{where}
GROUP BY 1
ORDER BY {order_alias} {direction}
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "vehicle" and plan.intent in {"ranking", "aggregation"}:
        if any("group by region" in n.lower() for n in plan.notes):
            joins, where = _automotive_filter_parts(plan, base_aliases={"c", "r"})
            extra_joins = "\n".join(joins)
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
{extra_joins}
{where}
GROUP BY 1, 2, 3, 4
ORDER BY {order_alias} {direction}
LIMIT {limit}
""".strip(),
            )
        joins, where = _automotive_filter_parts(plan, base_aliases={"c"})
        extra_joins = "\n".join(joins)
        filter_label = ", ".join(f.label for f in plan.filters) or "all body styles"
        metric_label = "revenue" if metric == "revenue" else "units"
        return TemplateHit(
            title=f"{'Lowest' if direction == 'ASC' else 'Top'} vehicles by {metric_label} ({filter_label})",
            glossary_matches=2 + len(plan.filters),
            sql=f"""
SELECT c.model, c.make, c.car_type,
       {select_metrics}
FROM automotive.fact_sales f
JOIN automotive.dim_carline c ON c.carline_id = f.carline_id
{extra_joins}
{where}
GROUP BY 1, 2, 3
ORDER BY {order_alias} {direction}
LIMIT {limit}
""".strip(),
        )

    if plan.entity == "metric_only" and plan.metric == "revenue":
        joins, value_where = _automotive_filter_parts(plan, base_aliases=set())
        extra_joins = "\n".join(joins)
        predicates = ["f.sales_date >= DATE '2024-01-01'"]
        if value_where:
            predicates.append(value_where.removeprefix("WHERE "))
        where = "WHERE " + " AND ".join(predicates)
        return TemplateHit(
            title="Revenue by month",
            glossary_matches=2,
            sql=f"""
SELECT date_trunc('month', f.sales_date)::date AS month,
       SUM(f.total_sales) AS revenue,
       SUM(f.order_qty) AS units_sold
FROM automotive.fact_sales f
{extra_joins}
{where}
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
SELECT date_trunc('month', f.sales_date)::date AS month,
       SUM(f.total_sales) AS revenue,
       SUM(f.order_qty) AS units_sold
FROM automotive.fact_sales f
WHERE f.sales_date >= DATE '2024-01-01'
GROUP BY 1
ORDER BY 1
LIMIT 36
""".strip(),
        )
    return None


def _insurance_filter_parts(
    plan: QuestionPlan,
    *,
    fact_alias: str,
    base_aliases: set[str],
) -> tuple[list[str], str]:
    aliases = set(base_aliases)
    joins: list[str] = []
    clauses: list[str] = []
    fact_table = "fact_claims" if fact_alias == "c" else "fact_policy_monthly"
    joins_by_table = {
        "insurance.dim_product": (
            "p",
            f"JOIN insurance.dim_product p ON p.product_id = {fact_alias}.product_id",
        ),
        "insurance.dim_region": (
            "r",
            f"JOIN insurance.dim_region r ON r.region_id = {fact_alias}.region_id",
        ),
        "insurance.dim_policy": (
            "po",
            f"JOIN insurance.dim_policy po ON po.policy_id = {fact_alias}.policy_id",
        ),
        "insurance.dim_agent": (
            "a",
            (
                f"JOIN insurance.dim_agent a ON a.agent_id = {fact_alias}.agent_id"
                if fact_table == "fact_policy_monthly"
                else "JOIN insurance.dim_policy po ON po.policy_id = c.policy_id\n"
                "JOIN insurance.dim_agent a ON a.agent_id = po.agent_id"
            ),
        ),
    }
    for filt in plan.filters:
        table, _, column = filt.column.rpartition(".")
        if table == "insurance.fact_claims":
            if fact_alias == "c":
                clauses.append(f"c.{column} {filt.operator} {_sql_literal(filt.value)}")
            continue
        mapping = joins_by_table.get(table)
        if mapping is None:
            continue
        alias, join = mapping
        if alias not in aliases:
            # Agent-on-claims join includes policy; record both aliases.
            joins.append(join)
            aliases.add(alias)
            if " dim_policy po " in f" {join} ":
                aliases.add("po")
        clauses.append(f"{alias}.{column} {filt.operator} {_sql_literal(filt.value)}")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return joins, where


def _insurance_from_plan(plan: QuestionPlan) -> TemplateHit | None:
    """Compile common insurance plans while preserving entity/value filters."""
    direction = plan.order_direction.upper()
    limit = plan.limit or 15

    if plan.metric == "loss_ratio" and plan.entity == "metric_only" and not plan.filters:
        return None  # use the grain-safe monthly fallback below
    if plan.metric == "frequency":
        return None  # cross-fact metric: leave to scoped LLM + validation

    premium_metrics = {"premium", "earned_premium", "renewal_rate"}
    use_premium = plan.metric in premium_metrics
    fact_alias = "pm" if use_premium else "c"
    fact_table = "insurance.fact_policy_monthly" if use_premium else "insurance.fact_claims"
    agent_join = (
        "insurance.dim_agent a ON a.agent_id = pm.agent_id"
        if use_premium
        else "insurance.dim_policy po ON po.policy_id = c.policy_id\n"
        "JOIN insurance.dim_agent a ON a.agent_id = po.agent_id"
    )
    dimensions = {
        "agent": ("a", "a.agent_name", "agent_name", agent_join),
        "product": (
            "p",
            "p.product_name",
            "product_name",
            f"insurance.dim_product p ON p.product_id = {fact_alias}.product_id",
        ),
        "policy": (
            "po",
            "po.policy_number",
            "policy_number",
            f"insurance.dim_policy po ON po.policy_id = {fact_alias}.policy_id",
        ),
        "customer": (
            "po",
            "po.customer_key",
            "customer_key",
            f"insurance.dim_policy po ON po.policy_id = {fact_alias}.policy_id",
        ),
        "region": (
            "r",
            "r.region_name",
            "region_name",
            f"insurance.dim_region r ON r.region_id = {fact_alias}.region_id",
        ),
        "claim": ("", "c.claim_status", "claim_status", ""),
    }
    if plan.entity not in dimensions:
        return None
    alias, dimension_expr, dimension_label, dimension_join = dimensions[plan.entity]
    base_aliases = {alias} if alias else set()
    if plan.entity == "agent" and not use_premium:
        base_aliases.add("po")
    joins, where = _insurance_filter_parts(
        plan,
        fact_alias=fact_alias,
        base_aliases=base_aliases,
    )
    join_lines = [f"JOIN {dimension_join}"] if dimension_join else []
    join_lines.extend(joins)

    metric_map = {
        "premium": ("SUM(pm.written_premium)", "written_premium"),
        "earned_premium": ("SUM(pm.earned_premium)", "earned_premium"),
        "renewal_rate": (
            "COUNT(*) FILTER (WHERE pm.renewed_flag)::numeric / "
            "NULLIF(COUNT(*) FILTER (WHERE pm.due_for_renewal_flag), 0)",
            "renewal_rate",
        ),
        "claims_incurred": ("SUM(c.incurred_amount)", "claims_incurred"),
        "severity": (
            "SUM(c.incurred_amount) / NULLIF(COUNT(DISTINCT c.claim_id), 0)",
            "average_claim_severity",
        ),
        "approval_rate": ("AVG(c.approved_flag::int)", "approval_rate"),
        "claim_count": ("COUNT(DISTINCT c.claim_id)", "claim_count"),
    }
    expression, metric_alias = metric_map.get(
        plan.metric,
        metric_map["premium" if use_premium else "claim_count"],
    )
    title_prefix = "Lowest" if direction == "ASC" else "Top"
    if plan.entity == "claim" and metric_alias == "claim_count":
        title = "Claim count by claim status"
    else:
        title = f"{title_prefix} insurance {dimension_label} by {metric_alias}"
    return TemplateHit(
        title=title,
        glossary_matches=2 + len(plan.filters),
        sql=f"""
SELECT {dimension_expr} AS {dimension_label},
       {expression} AS {metric_alias}
FROM {fact_table} {fact_alias}
{chr(10).join(join_lines)}
{where}
GROUP BY 1
ORDER BY {metric_alias} {direction}
LIMIT {limit}
""".strip(),
    )


def _insurance_templates(q: str) -> TemplateHit | None:
    if re.search(r"loss\s*ratio", q):
        return TemplateHit(
            title="Loss ratio by month",
            glossary_matches=2,
            sql="""
WITH claims AS (
  SELECT date_trunc('month', c.reported_date)::date AS month,
         SUM(c.incurred_amount) AS claims_incurred
  FROM insurance.fact_claims c
  WHERE c.reported_date >= DATE '2024-01-01'
  GROUP BY 1
),
premium AS (
  SELECT date_trunc('month', pm.accounting_month)::date AS month,
         SUM(pm.earned_premium) AS earned_premium
  FROM insurance.fact_policy_monthly pm
  WHERE pm.accounting_month >= DATE '2024-01-01'
  GROUP BY 1
)
SELECT COALESCE(ca.month, p.month) AS month,
       COALESCE(ca.claims_incurred, 0) AS claims_incurred,
       COALESCE(p.earned_premium, 0) AS earned_premium,
       COALESCE(ca.claims_incurred, 0)
         / NULLIF(p.earned_premium, 0) AS loss_ratio
FROM claims ca
FULL OUTER JOIN premium p ON p.month = ca.month
ORDER BY month
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
