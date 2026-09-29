"""Deterministic NLQ templates so chat works without an LLM key."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.core.config import Industry
from app.services.chat.question_understanding import (
    QuestionPlan,
    filter_predicate,
    understand_question,
)
from app.services.chat.semantic_analytics import (
    SemanticCompileError,
    compile_analytical_query,
    time_scope_clauses,
)
from app.services.chat.time_periods import anchor_sql, period_predicate


@dataclass(frozen=True, slots=True)
class TemplateHit:
    sql: str
    title: str
    glossary_matches: int
    path: str = "template"
    # Wide comparison results chart one series per compared value.
    series: tuple[str, ...] = ()


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

    if industry is Industry.AUTOMOTIVE:
        special = _automotive_business_shape(plan)
        if special is not None:
            return special
    elif pack is not None:
        governed = _insurance_governed(plan, pack)
        if governed is not None:
            return governed

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
    if metric == "average_selling_price":
        return (
            "SUM(f.total_sales) / NULLIF(SUM(f.order_qty), 0) AS average_selling_price",
            "average_selling_price",
        )
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
        clauses.append(filter_predicate(f"{alias}.{column}", filt))
    if plan.period is not None:
        clauses.append(
            period_predicate(plan.period, "f.sales_date", anchor_sql("automotive.fact_sales", "sales_date"))
        )
    elif plan.year_filter:
        clauses.append(f"EXTRACT(YEAR FROM f.sales_date)::int = {int(plan.year_filter)}")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return joins, where


def _governed_automotive(plan: QuestionPlan) -> TemplateHit | None:
    """Pack-free SQL for business questions the legacy entity templates skip."""
    if plan.industry is not Industry.AUTOMOTIVE:
        return None
    if plan.analysis == "year_window_compare":
        return _year_window_sql(plan)
    if plan.analysis == "period_growth":
        return _growth_sql(plan)
    if plan.has_time_scope or "year" in plan.dimensions:
        if plan.metric in {"revenue", "orders", "units", "average_selling_price"}:
            return _dimension_breakdown_sql(plan if plan.dimensions else _with_month(plan))
    if plan.entity != "metric_only":
        return None
    if plan.metric not in {"revenue", "orders", "units", "average_selling_price"}:
        return None
    if plan.dimensions:
        return _dimension_breakdown_sql(plan)
    if plan.metric in {"orders", "units"} or plan.filters:
        # A named metric with no grain still deserves a time series, not a failure.
        return _dimension_breakdown_sql(
            _with_month(plan) if not plan.time_grain else plan,
        )
    return None


def _with_month(plan: QuestionPlan) -> QuestionPlan:
    plan.dimensions = ["month", *plan.dimensions]
    plan.time_grain = "month"
    plan.intent = "trend"
    return plan


def _year_window_sql(plan: QuestionPlan) -> TemplateHit:
    months = max(1, min(plan.window_months or 3, 12))
    years = max(1, min(plan.window_years or 3, 10))
    metrics, _alias = _order_metric(plan.metric if plan.metric != "unknown" else "revenue")
    return TemplateHit(
        title=f"Last {months} months compared across {years} years",
        glossary_matches=3,
        path="semantic_compiler",
        sql=f"""
SELECT EXTRACT(YEAR FROM f.sales_date)::int AS year,
       date_trunc('month', f.sales_date)::date AS month,
       {metrics}
FROM automotive.fact_sales f
WHERE f.sales_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '{years} years'
  AND f.sales_date < date_trunc('month', CURRENT_DATE)
  AND EXTRACT(MONTH FROM f.sales_date)::int IN (
        SELECT EXTRACT(MONTH FROM date_trunc('month', CURRENT_DATE) - (n || ' months')::interval)::int
        FROM generate_series(1, {months}) AS n
      )
GROUP BY 1, 2
ORDER BY 1, 2
LIMIT 36
""".strip(),
    )


def _growth_sql(plan: QuestionPlan) -> TemplateHit:
    metrics, alias = _order_metric(plan.metric if plan.metric != "unknown" else "revenue")
    label = "yoy_growth_pct" if plan.time_grain == "year" else "mom_growth_pct"
    grain_key = "year" if plan.time_grain == "year" else "month"
    grain_expr, grain_alias, _grain_join = _DIM_EXPR[grain_key]
    extras = [key for key in plan.dimensions if key not in {"month", "quarter", "year"} and key in _DIM_EXPR]
    selects = [f"{grain_expr} AS {grain_alias}"]
    joins: list[str] = []
    aliases: set[str] = set()
    for key in extras:
        expr, dim_alias, join = _DIM_EXPR[key]
        selects.append(f"{expr} AS {dim_alias}")
        if join and join not in joins:
            joins.append(join)
            if " dim_region " in f" {join} ":
                aliases.add("r")
            if " dim_carline " in f" {join} ":
                aliases.add("c")
    extra_joins, where = _automotive_filter_parts(plan, base_aliases=aliases)
    for join in extra_joins:
        if join not in joins:
            joins.append(join)
    partition = ", ".join(_DIM_EXPR[key][1] for key in extras)
    partition_sql = f"PARTITION BY {partition} " if partition else ""
    group_cols = ", ".join(str(index) for index in range(1, len(selects) + 1))
    order_cols = ", ".join(str(index) for index in range(1, len(selects) + 1))
    return TemplateHit(
        title=f"{alias.replace('_', ' ').title()} growth",
        glossary_matches=2,
        path="semantic_compiler",
        sql=f"""
WITH aggregated AS (
  SELECT {", ".join(selects)},
         {metrics}
  FROM automotive.fact_sales f
  {chr(10).join(joins)}
  {where}
  GROUP BY {group_cols}
)
SELECT aggregated.*,
       LAG({alias}) OVER ({partition_sql}ORDER BY {grain_alias}) AS previous_{alias},
       100.0 * ({alias} - LAG({alias}) OVER ({partition_sql}ORDER BY {grain_alias}))
         / NULLIF(LAG({alias}) OVER ({partition_sql}ORDER BY {grain_alias}), 0) AS {label}
FROM aggregated
ORDER BY {order_cols}
LIMIT 36
""".strip(),
    )


_DIM_EXPR: dict[str, tuple[str, str, str | None]] = {
    "year": ("EXTRACT(YEAR FROM f.sales_date)::int", "year", None),
    "quarter": ("date_trunc('quarter', f.sales_date)::date", "quarter", None),
    "month": ("date_trunc('month', f.sales_date)::date", "month", None),
    "region": (
        "COALESCE(r.region_name, 'Unknown')",
        "region_name",
        "LEFT JOIN automotive.dim_region r ON r.region_id = f.region_id",
    ),
    "city": (
        "r.city",
        "city",
        "LEFT JOIN automotive.dim_region r ON r.region_id = f.region_id",
    ),
    "car_type": (
        "c.car_type",
        "car_type",
        "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id",
    ),
    "engine_type": (
        "c.engine_type",
        "engine_type",
        "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id",
    ),
    "model": (
        "c.model",
        "model",
        "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id",
    ),
    "make": (
        "c.make",
        "make",
        "JOIN automotive.dim_carline c ON c.carline_id = f.carline_id",
    ),
    "dealer": (
        "d.dealer_name",
        "dealer_name",
        "JOIN automotive.dim_dealer d ON d.dealer_id = f.dealer_id",
    ),
}


_TIME_KEYS = ("year", "quarter", "month")
_TREND_MONTHS = 24
# Monthly trends without a year show the latest window, not the oldest rows.
_RECENT_MONTHS = (
    "f.sales_date >= (SELECT date_trunc('month', MAX(latest.sales_date)) "
    f"FROM automotive.fact_sales latest) - INTERVAL '{_TREND_MONTHS - 1} months'"
)
_FILTER_KEY_COLUMN = {
    "make": "make",
    "model": "model",
    "car_type": "car_type",
    "engine_type": "engine_type",
    "city": "city",
    "region": "region_name",
}


def _dimension_joins(dims: list[str]) -> tuple[list[str], list[str], set[str]]:
    selects: list[str] = []
    joins: list[str] = []
    aliases: set[str] = set()
    for key in dims:
        expr, alias, join = _DIM_EXPR[key]
        selects.append(f"{expr} AS {alias}")
        if join and join not in joins:
            joins.append(join)
            if " dim_region " in f" {join} ":
                aliases.add("r")
            if " dim_carline " in f" {join} ":
                aliases.add("c")
            if " dim_dealer " in f" {join} ":
                aliases.add("d")
    return selects, joins, aliases


def _where_with(where: str, *predicates: str) -> str:
    parts = [where.removeprefix("WHERE ")] if where else []
    parts.extend(predicate for predicate in predicates if predicate)
    return "WHERE " + " AND ".join(parts) if parts else ""


def _dimension_breakdown_sql(plan: QuestionPlan) -> TemplateHit | None:
    dims = [key for key in plan.dimensions if key in _DIM_EXPR] or ["month"]
    selects, joins, aliases = _dimension_joins(dims)
    extra_joins, where = _automotive_filter_parts(plan, base_aliases=aliases)
    for join in extra_joins:
        if join not in joins:
            joins.append(join)
    metrics, order_alias = _order_metric(plan.metric if plan.metric != "unknown" else "revenue")
    chronological = any(key in dims for key in _TIME_KEYS)
    if "month" in dims and not plan.has_time_scope:
        where = _where_with(where, _RECENT_MONTHS)
    order = (
        ", ".join(str(i) for i in range(1, len(selects) + 1))
        if chronological
        else f"{order_alias} {plan.order_direction.upper()}"
    )
    limit = 100 if chronological else max(1, min(plan.limit or 36, 100))
    title_dims = ", ".join(alias for _expr, alias, _join in (_DIM_EXPR[key] for key in dims))
    return TemplateHit(
        title=f"{order_alias.replace('_', ' ').title()} by {title_dims}",
        glossary_matches=max(2, len(dims) + 1),
        path="semantic_compiler",
        sql=f"""
SELECT {", ".join(selects)},
       {metrics}
FROM automotive.fact_sales f
{chr(10).join(joins)}
{where}
GROUP BY {", ".join(str(i) for i in range(1, len(selects) + 1))}
ORDER BY {order}
LIMIT {limit}
""".strip(),
    )


def _automotive_business_shape(plan: QuestionPlan) -> TemplateHit | None:
    """Market share and side-by-side comparisons need shapes the compiler lacks."""
    if plan.metric not in {"revenue", "units", "orders", "average_selling_price"}:
        return None
    if plan.analysis == "market_share":
        return _market_share_sql(plan)
    if plan.intent == "comparison" and plan.analysis in {"basic", "breakdown"}:
        return _comparison_pivot_sql(plan)
    return None


def _market_share_sql(plan: QuestionPlan) -> TemplateHit | None:
    time_keys = [key for key in plan.dimensions if key in _TIME_KEYS][:1]
    share_key = next(
        (key for key in plan.dimensions if key in _FILTER_KEY_COLUMN and key not in _TIME_KEYS),
        "make",
    )
    share_column = _FILTER_KEY_COLUMN[share_key]
    focus = [f for f in plan.filters if f.column.rsplit(".", 1)[-1] == share_column]
    scoped = replace(plan, filters=[f for f in plan.filters if f not in focus])
    dims = [*time_keys, share_key]
    selects, joins, aliases = _dimension_joins(dims)
    extra_joins, where = _automotive_filter_parts(scoped, base_aliases=aliases)
    for join in extra_joins:
        if join not in joins:
            joins.append(join)
    if "month" in time_keys and not plan.has_time_scope:
        where = _where_with(where, _RECENT_MONTHS)
    metric = "revenue" if plan.metric == "revenue" else "units_sold"
    dim_aliases = [_DIM_EXPR[key][1] for key in dims]
    time_aliases = dim_aliases[:-1]
    share_alias = dim_aliases[-1]
    partition = f"PARTITION BY {', '.join(time_aliases)}" if time_aliases else ""
    outer_where = ""
    if focus:
        values = [value for f in focus for value in f.all_values]
        outer_where = f"WHERE {share_alias} IN ({', '.join(_sql_literal(v) for v in values)})"
    order = ", ".join([*time_aliases, "market_share_pct DESC"])
    group_cols = ", ".join(str(i) for i in range(1, len(selects) + 1))
    return TemplateHit(
        title=f"Market share by {share_alias.replace('_', ' ')} ({metric.replace('_', ' ')})",
        glossary_matches=3,
        path="semantic_compiler",
        sql=f"""
WITH base AS (
  SELECT {", ".join(selects)},
         SUM(f.order_qty) AS units_sold,
         SUM(f.total_sales) AS revenue
  FROM automotive.fact_sales f
  {chr(10).join(joins)}
  {where}
  GROUP BY {group_cols}
), shared AS (
  SELECT base.*,
         100.0 * {metric} / NULLIF(SUM({metric}) OVER ({partition}), 0) AS market_share_pct
  FROM base
)
SELECT {", ".join(dim_aliases)}, market_share_pct, units_sold, revenue
FROM shared
{outer_where}
ORDER BY {order}
LIMIT 100
""".strip(),
    )


_PIVOT_METRIC = {
    "revenue": ("SUM(f.total_sales) FILTER (WHERE {cond})", "revenue"),
    "units": ("SUM(f.order_qty) FILTER (WHERE {cond})", "units_sold"),
    "orders": ("COUNT(DISTINCT f.order_id) FILTER (WHERE {cond})", "orders"),
    "average_selling_price": (
        "SUM(f.total_sales) FILTER (WHERE {cond}) / "
        "NULLIF(SUM(f.order_qty) FILTER (WHERE {cond}), 0)",
        "average_selling_price",
    ),
}


def _column_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug if slug and not slug[0].isdigit() else f"v_{slug}"


def _comparison_pivot_sql(plan: QuestionPlan) -> TemplateHit | None:
    """One column per compared value over time: year | mg_revenue | maruti_suzuki_revenue."""
    time_keys = [key for key in plan.dimensions if key in _TIME_KEYS]
    other = [key for key in plan.dimensions if key not in _TIME_KEYS]
    if len(time_keys) != 1 or len(other) != 1 or other[0] not in _FILTER_KEY_COLUMN:
        return None
    compare_key = other[0]
    column = _FILTER_KEY_COLUMN[compare_key]
    compared = next(
        (
            f
            for f in plan.filters
            if f.column.rsplit(".", 1)[-1] == column and len(f.all_values) > 1
        ),
        None,
    )
    if compared is None or len(compared.all_values) > 6:
        return None
    expr, _alias, join = _DIM_EXPR[compare_key]
    selects, joins, aliases = _dimension_joins(time_keys)
    if join and join not in joins:
        joins.append(join)
        aliases.add("r" if " dim_region " in f" {join} " else "c")
    extra_joins, where = _automotive_filter_parts(plan, base_aliases=aliases)
    for extra in extra_joins:
        if extra not in joins:
            joins.append(extra)
    if "month" in time_keys and not plan.has_time_scope:
        where = _where_with(where, _RECENT_MONTHS)
    template, suffix = _PIVOT_METRIC[plan.metric]
    series: list[str] = []
    for value in compared.all_values:
        name = f"{_column_slug(value)}_{suffix}"
        series.append(name)
        selects.append(f"{template.format(cond=f'{expr} = {_sql_literal(value)}')} AS {name}")
    time_alias = _DIM_EXPR[time_keys[0]][1]
    return TemplateHit(
        title=f"{' vs '.join(compared.all_values)} — {suffix.replace('_', ' ')} by {time_alias}",
        glossary_matches=3,
        path="semantic_compiler",
        series=tuple(series),
        sql=f"""
SELECT {(',' + chr(10) + '       ').join(selects)}
FROM automotive.fact_sales f
{chr(10).join(joins)}
{where}
GROUP BY 1
ORDER BY 1
LIMIT 100
""".strip(),
    )


def _automotive_from_plan(plan: QuestionPlan) -> TemplateHit | None:
    governed = _governed_automotive(plan)
    if governed is not None:
        return governed

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
                clauses.append(filter_predicate(f"c.{column}", filt))
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
        clauses.append(filter_predicate(f"{alias}.{column}", filt))
    clauses.extend(
        time_scope_clauses(
            plan,
            alias=fact_alias,
            physical_table=f"insurance.{fact_table}",
            date_column="reported_date" if fact_alias == "c" else "accounting_month",
            default_window=False,
        )
    )
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return joins, where


_INSURANCE_COMPILED = frozenset(
    {
        "premium",
        "earned_premium",
        "renewal_rate",
        "claims_incurred",
        "claims_paid",
        "claim_count",
        "severity",
        "approval_rate",
    }
)
# Cross-fact ratios: (claims numerator, premium denominator, ratio alias).
_INSURANCE_RATIOS: dict[str, tuple[tuple[str, str], tuple[str, str], str]] = {
    "loss_ratio": (
        ("SUM(c.incurred_amount)", "claims_incurred"),
        ("SUM(pm.earned_premium)", "earned_premium"),
        "loss_ratio",
    ),
    "frequency": (
        ("COUNT(DISTINCT c.claim_id)", "claim_count"),
        ("SUM(pm.exposure_units)", "exposure_units"),
        "claim_frequency",
    ),
}
_INSURANCE_DIMENSION_COLUMNS: dict[str, tuple[str, str]] = {
    "product": ("insurance.dim_product", "product_name"),
    "line_of_business": ("insurance.dim_product", "line_of_business"),
    "product_family": ("insurance.dim_product", "product_family"),
    "coverage_type": ("insurance.dim_product", "coverage_type"),
    "region": ("insurance.dim_region", "region_name"),
    "state": ("insurance.dim_region", "state_name"),
    "agent": ("insurance.dim_agent", "agent_name"),
    "channel": ("insurance.dim_agent", "channel_name"),
    "branch": ("insurance.dim_agent", "branch_name"),
    "coverage_tier": ("insurance.dim_policy", "coverage_tier"),
    "policy_status": ("insurance.dim_policy", "policy_status"),
}
_INSURANCE_TABLE_KEYS: dict[str, tuple[str, str]] = {
    "insurance.dim_product": ("p", "product_id"),
    "insurance.dim_region": ("r", "region_id"),
    "insurance.dim_agent": ("a", "agent_id"),
    "insurance.dim_policy": ("po", "policy_id"),
}


def _insurance_governed(plan: QuestionPlan, pack: object) -> TemplateHit | None:
    """Semantic-compiled insurance answers that keep every filter and period."""
    if plan.metric in _INSURANCE_RATIOS:
        return _insurance_ratio_sql(plan)
    if plan.metric not in _INSURANCE_COMPILED:
        return None
    if not plan.dimensions:
        plan.dimensions = ["month"]
        plan.time_grain = "month"
        if plan.intent in {"aggregation", "unknown"}:
            plan.intent = "trend"
    try:
        compiled = compile_analytical_query(plan, pack, force=True)
    except SemanticCompileError:
        return None
    if compiled is None:
        return None
    return TemplateHit(
        sql=compiled.sql,
        title=compiled.title,
        glossary_matches=max(2, len(plan.dimensions) + 1),
        path="semantic_compiler",
    )


def _insurance_side(
    plan: QuestionPlan,
    *,
    fact_table: str,
    fact_alias: str,
    date_column: str,
    measure: tuple[str, str],
) -> tuple[str, list[str]]:
    """One aggregated CTE body of a cross-fact ratio; returns (sql, output aliases)."""
    joins: list[str] = []

    def need(table: str) -> str:
        alias, key = _INSURANCE_TABLE_KEYS[table]
        if table == "insurance.dim_agent" and fact_alias == "c":
            # Claims reach the selling agent through the policy.
            wanted = [
                "JOIN insurance.dim_policy po ON po.policy_id = c.policy_id",
                "JOIN insurance.dim_agent a ON a.agent_id = po.agent_id",
            ]
        else:
            wanted = [f"JOIN {table} {alias} ON {alias}.{key} = {fact_alias}.{key}"]
        joins.extend(join for join in wanted if join not in joins)
        return alias

    selects: list[str] = []
    aliases: list[str] = []
    for key in plan.dimensions:
        column = f"{fact_alias}.{date_column}"
        if key == "year":
            expression, name = f"EXTRACT(YEAR FROM {column})::int", "year"
        elif key in {"month", "quarter"}:
            expression, name = f"date_trunc('{key}', {column})::date", key
        else:
            table, name = _INSURANCE_DIMENSION_COLUMNS[key]
            expression = f"{need(table)}.{name}"
        selects.append(f"{expression} AS {name}")
        aliases.append(name)
    clauses: list[str] = []
    for filt in plan.filters:
        table, _, column = filt.column.rpartition(".")
        if table.startswith("insurance.fact_"):
            if table == fact_table:
                clauses.append(filter_predicate(f"{fact_alias}.{column}", filt))
            continue
        if table in _INSURANCE_TABLE_KEYS:
            clauses.append(filter_predicate(f"{need(table)}.{column}", filt))
    clauses.extend(
        time_scope_clauses(
            plan,
            alias=fact_alias,
            physical_table=fact_table,
            date_column=date_column,
            default_window=True,
        )
    )
    expression, name = measure
    body = (
        f"SELECT {', '.join([*selects, f'{expression} AS {name}'])}\n"
        f"  FROM {fact_table} {fact_alias}\n"
        + "".join(f"  {join}\n" for join in joins)
        + (f"  WHERE {' AND '.join(clauses)}\n" if clauses else "")
        + (f"  GROUP BY {', '.join(str(i) for i in range(1, len(selects) + 1))}" if selects else "")
    )
    return body.rstrip(), aliases


def _insurance_ratio_sql(plan: QuestionPlan) -> TemplateHit | None:
    """Loss ratio / claim frequency: aggregate each fact at the same grain, then divide."""
    if any(
        key not in _INSURANCE_DIMENSION_COLUMNS and key not in _TIME_KEYS for key in plan.dimensions
    ):
        return None  # claim-only groupings (status, type) have no premium side
    numerator, denominator, ratio = _INSURANCE_RATIOS[plan.metric]
    claims_sql, keys = _insurance_side(
        plan,
        fact_table="insurance.fact_claims",
        fact_alias="c",
        date_column="reported_date",
        measure=numerator,
    )
    premium_sql, _ = _insurance_side(
        plan,
        fact_table="insurance.fact_policy_monthly",
        fact_alias="pm",
        date_column="accounting_month",
        measure=denominator,
    )
    num, den = numerator[1], denominator[1]
    outputs = [f"COALESCE(cl.{key}, pr.{key}) AS {key}" for key in keys]
    joined = (
        "FROM claims cl\nFULL OUTER JOIN premium pr ON "
        + " AND ".join(f"pr.{key} = cl.{key}" for key in keys)
        if keys
        else "FROM claims cl\nCROSS JOIN premium pr"
    )
    chronological = any(key in _TIME_KEYS for key in keys)
    order = (
        ", ".join(str(i) for i in range(1, len(keys) + 1))
        if chronological
        else f"{ratio} {plan.order_direction.upper()} NULLS LAST"
    )
    limit = 100 if chronological else max(1, min(plan.limit or 20, 100))
    grain = ", ".join(keys) or "total"
    return TemplateHit(
        title=f"{ratio.replace('_', ' ').title()} by {grain}",
        glossary_matches=3,
        path="semantic_compiler",
        sql=f"""
WITH claims AS (
  {claims_sql}
),
premium AS (
  {premium_sql}
)
SELECT {', '.join([*outputs, f'COALESCE(cl.{num}, 0) AS {num}', f'COALESCE(pr.{den}, 0) AS {den}'])},
       COALESCE(cl.{num}, 0)::numeric / NULLIF(pr.{den}, 0) AS {ratio}
{joined}
ORDER BY {order}
LIMIT {limit}
""".strip(),
    )


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
