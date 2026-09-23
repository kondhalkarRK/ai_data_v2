"""Semantic analytical planner/compiler for advanced NLQ shapes.

The compiler consumes a structured ``QuestionPlan`` and the validated active
semantic pack. It intentionally supports a bounded set of governed analytical
operations instead of asking an LLM to invent joins or SQL structure.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from app.core.config import Industry
from app.services.chat.question_understanding import QuestionPlan


@dataclass(frozen=True, slots=True)
class DimensionSpec:
    key: str
    table: str
    column: str
    alias: str
    expression: str | None = None
    time_grain: str | None = None


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: str
    table: str
    expression: str
    alias: str


@dataclass(frozen=True, slots=True)
class AnalyticalQuery:
    sql: str
    title: str
    dimensions: tuple[str, ...]
    metric: str
    required_tables: tuple[str, ...]


class SemanticCompileError(ValueError):
    """The requested analytical shape is not valid for the active semantic pack."""


_ALIASES = {
    "fact_sales": "f",
    "dim_carline": "v",
    "dim_color": "co",
    "dim_salesman": "s",
    "dim_region": "r",
    "dim_dealer": "d",
    "dim_targets": "t",
    "fact_policy_monthly": "pm",
    "fact_claims": "cl",
    "dim_policy": "po",
    "dim_product": "p",
    "dim_agent": "a",
}


_AUTOMOTIVE_DIMENSIONS = {
    "month": DimensionSpec(
        "month",
        "fact_sales",
        "sales_date",
        "month",
        "date_trunc('month', {alias}.sales_date)::date",
        "month",
    ),
    "quarter": DimensionSpec(
        "quarter",
        "fact_sales",
        "sales_date",
        "quarter",
        "date_trunc('quarter', {alias}.sales_date)::date",
        "quarter",
    ),
    "year": DimensionSpec(
        "year",
        "fact_sales",
        "sales_date",
        "year",
        "EXTRACT(YEAR FROM {alias}.sales_date)::int",
        "year",
    ),
    "car_type": DimensionSpec("car_type", "dim_carline", "car_type", "car_type"),
    "colour": DimensionSpec("colour", "dim_color", "colour_name", "colour_name"),
    "make": DimensionSpec("make", "dim_carline", "make", "make"),
    "model": DimensionSpec("model", "dim_carline", "model", "model"),
    "dealer": DimensionSpec("dealer", "dim_dealer", "dealer_name", "dealer_name"),
    "salesperson": DimensionSpec(
        "salesperson",
        "dim_salesman",
        "first_name",
        "salesperson_name",
        "({alias}.first_name || ' ' || {alias}.last_name)",
    ),
    "region": DimensionSpec("region", "dim_region", "region_name", "region_name"),
    "city": DimensionSpec("city", "dim_region", "city", "city"),
    "state": DimensionSpec("state", "dim_region", "state_code", "state_code"),
}


_INSURANCE_DIMENSIONS = {
    "product": DimensionSpec("product", "dim_product", "product_name", "product_name"),
    "product_family": DimensionSpec(
        "product_family", "dim_product", "product_family", "product_family"
    ),
    "line_of_business": DimensionSpec(
        "line_of_business", "dim_product", "line_of_business", "line_of_business"
    ),
    "customer": DimensionSpec("customer", "dim_policy", "customer_key", "customer_key"),
    "policy": DimensionSpec("policy", "dim_policy", "policy_number", "policy_number"),
    "agent": DimensionSpec("agent", "dim_agent", "agent_name", "agent_name"),
    "channel": DimensionSpec("channel", "dim_agent", "channel_name", "channel_name"),
    "branch": DimensionSpec("branch", "dim_agent", "branch_name", "branch_name"),
    "region": DimensionSpec("region", "dim_region", "region_name", "region_name"),
    "state": DimensionSpec("state", "dim_region", "state_name", "state_name"),
    "claim_status": DimensionSpec(
        "claim_status", "fact_claims", "claim_status", "claim_status"
    ),
}


def _metric_spec(plan: QuestionPlan) -> MetricSpec:
    if plan.industry is Industry.AUTOMOTIVE:
        specs = {
            "revenue": MetricSpec("revenue", "fact_sales", "SUM({alias}.total_sales)", "revenue"),
            "units": MetricSpec("units", "fact_sales", "SUM({alias}.order_qty)", "units_sold"),
            "orders": MetricSpec(
                "orders",
                "fact_sales",
                "COUNT(DISTINCT {alias}.order_id)",
                "orders",
            ),
        }
    else:
        specs = {
            "premium": MetricSpec(
                "premium",
                "fact_policy_monthly",
                "SUM({alias}.written_premium)",
                "written_premium",
            ),
            "earned_premium": MetricSpec(
                "earned_premium",
                "fact_policy_monthly",
                "SUM({alias}.earned_premium)",
                "earned_premium",
            ),
            "renewal_rate": MetricSpec(
                "renewal_rate",
                "fact_policy_monthly",
                "COUNT(*) FILTER (WHERE {alias}.renewed_flag)::numeric / "
                "NULLIF(COUNT(*) FILTER (WHERE {alias}.due_for_renewal_flag), 0)",
                "renewal_rate",
            ),
            "claims_incurred": MetricSpec(
                "claims_incurred",
                "fact_claims",
                "SUM({alias}.incurred_amount)",
                "claims_incurred",
            ),
            "claim_count": MetricSpec(
                "claim_count",
                "fact_claims",
                "COUNT(DISTINCT {alias}.claim_id)",
                "claim_count",
            ),
            "severity": MetricSpec(
                "severity",
                "fact_claims",
                "SUM({alias}.incurred_amount) / "
                "NULLIF(COUNT(DISTINCT {alias}.claim_id), 0)",
                "average_claim_severity",
            ),
            "approval_rate": MetricSpec(
                "approval_rate",
                "fact_claims",
                "AVG({alias}.approved_flag::int)",
                "approval_rate",
            ),
        }
    spec = specs.get(plan.metric)
    if spec is None:
        raise SemanticCompileError(
            f"Metric '{plan.metric}' requires a specialised cross-fact plan"
        )
    return spec


def _dimension_specs(plan: QuestionPlan, base_table: str) -> list[DimensionSpec]:
    catalog = (
        _AUTOMOTIVE_DIMENSIONS
        if plan.industry is Industry.AUTOMOTIVE
        else dict(_INSURANCE_DIMENSIONS)
    )
    if plan.industry is Industry.INSURANCE:
        date_column = "accounting_month" if base_table == "fact_policy_monthly" else "reported_date"
        for grain, expression in {
            "month": f"date_trunc('month', {{alias}}.{date_column})::date",
            "quarter": f"date_trunc('quarter', {{alias}}.{date_column})::date",
            "year": f"EXTRACT(YEAR FROM {{alias}}.{date_column})::int",
        }.items():
            catalog[grain] = DimensionSpec(
                grain, base_table, date_column, grain, expression, grain
            )
    specs: list[DimensionSpec] = []
    for key in plan.dimensions:
        spec = catalog.get(key)
        if spec is None:
            raise SemanticCompileError(f"Unknown dimension '{key}'")
        if spec.table.startswith("fact_") and spec.table != base_table:
            raise SemanticCompileError(
                f"Dimension '{key}' is not compatible with metric grain '{base_table}'"
            )
        specs.append(spec)
    return specs


def _model_tables(pack: Any) -> dict[str, Any]:
    model = getattr(pack, "model", None)
    return dict(getattr(model, "tables", {}) or {})


def _validate_specs(
    pack: Any,
    metric: MetricSpec,
    dimensions: list[DimensionSpec],
) -> None:
    tables = _model_tables(pack)
    if metric.table not in tables:
        raise SemanticCompileError(f"Metric table '{metric.table}' is not in semantic pack")
    for spec in dimensions:
        table = tables.get(spec.table)
        columns = getattr(table, "columns", {}) if table is not None else {}
        if table is None or spec.column not in columns:
            raise SemanticCompileError(
                f"Dimension '{spec.key}' does not map to a declared semantic column"
            )


def _relationship_path(pack: Any, start: str, target: str) -> list[Any]:
    if start == target:
        return []
    relationships = list(getattr(getattr(pack, "model", None), "relationships", []) or [])
    graph: dict[str, list[tuple[str, Any]]] = {}
    for rel in relationships:
        graph.setdefault(rel.from_table, []).append((rel.to_table, rel))
        graph.setdefault(rel.to_table, []).append((rel.from_table, rel))
    queue: deque[tuple[str, list[Any]]] = deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        for neighbor, rel in graph.get(node, []):
            if neighbor in seen:
                continue
            next_path = [*path, rel]
            if neighbor == target:
                return next_path
            seen.add(neighbor)
            queue.append((neighbor, next_path))
    raise SemanticCompileError(f"No semantic join path from {start} to {target}")


def _join_clauses(pack: Any, base_table: str, required_tables: set[str]) -> list[str]:
    tables = _model_tables(pack)
    joined = {base_table}
    clauses: list[str] = []
    emitted: set[str] = set()
    for target in sorted(required_tables):
        for rel in _relationship_path(pack, base_table, target):
            if rel.name in emitted:
                joined.update({rel.from_table, rel.to_table})
                continue
            if rel.from_table in joined:
                source, source_col = rel.from_table, rel.from_column
                dest, dest_col = rel.to_table, rel.to_column
            elif rel.to_table in joined:
                source, source_col = rel.to_table, rel.to_column
                dest, dest_col = rel.from_table, rel.from_column
            else:
                # The path is ordered from base, so this only occurs after a duplicate edge.
                source, source_col = rel.from_table, rel.from_column
                dest, dest_col = rel.to_table, rel.to_column
            physical = getattr(tables[dest], "physical_name", dest)
            clauses.append(
                f"JOIN {physical} {_ALIASES[dest]} ON "
                f"{_ALIASES[dest]}.{dest_col} = {_ALIASES[source]}.{source_col}"
            )
            joined.add(dest)
            emitted.add(rel.name)
    return clauses


def _dimension_expression(spec: DimensionSpec) -> str:
    alias = _ALIASES[spec.table]
    return (
        spec.expression.format(alias=alias)
        if spec.expression
        else f"{alias}.{spec.column}"
    )


def _logical_table_for_physical(pack: Any, physical: str) -> str | None:
    physical = physical.lower()
    for logical, table in _model_tables(pack).items():
        if str(getattr(table, "physical_name", logical)).lower() == physical:
            return logical
    return None


def _where_clauses(plan: QuestionPlan, pack: Any, required_tables: set[str]) -> list[str]:
    clauses: list[str] = []
    for filt in plan.filters:
        physical_table, _, column = filt.column.rpartition(".")
        logical = _logical_table_for_physical(pack, physical_table)
        if logical is None:
            raise SemanticCompileError(f"Filter table '{physical_table}' is not in semantic pack")
        required_tables.add(logical)
        table = _model_tables(pack)[logical]
        if column not in (getattr(table, "columns", {}) or {}):
            raise SemanticCompileError(f"Filter column '{filt.column}' is not in semantic pack")
        if filt.operator not in {"=", "!=", "<>", ">", ">=", "<", "<="}:
            raise SemanticCompileError(f"Unsupported filter operator '{filt.operator}'")
        value = filt.value.replace("'", "''")
        clauses.append(f"{_ALIASES[logical]}.{column} {filt.operator} '{value}'")
    return clauses


def _partition_aliases(plan: QuestionPlan, dimensions: list[DimensionSpec]) -> list[str]:
    wanted = set(plan.partition_by)
    return [spec.alias for spec in dimensions if spec.key in wanted]


def _window_order_alias(dimensions: list[DimensionSpec]) -> str:
    for spec in dimensions:
        if spec.time_grain:
            return spec.alias
    return dimensions[0].alias if dimensions else "1"


def _render_advanced_sql(
    plan: QuestionPlan,
    dimension_specs: list[DimensionSpec],
    metric: MetricSpec,
    from_sql: str,
    joins: list[str],
    where: list[str],
) -> str:
    expressions = [_dimension_expression(spec) for spec in dimension_specs]
    dim_select = ",\n       ".join(
        f"{expression} AS {spec.alias}"
        for expression, spec in zip(expressions, dimension_specs, strict=True)
    )
    base_alias = _ALIASES[metric.table]
    metric_expression = metric.expression.format(alias=base_alias)
    select_lines = [line for line in (dim_select, f"{metric_expression} AS {metric.alias}") if line]
    group_by = ", ".join(expressions)
    aggregate = (
        "SELECT "
        + ",\n       ".join(select_lines)
        + f"\nFROM {from_sql} {base_alias}"
        + (f"\n{chr(10).join(joins)}" if joins else "")
        + (f"\nWHERE {' AND '.join(where)}" if where else "")
        + (f"\nGROUP BY {group_by}" if group_by else "")
    )
    dimension_aliases = [spec.alias for spec in dimension_specs]
    partition = _partition_aliases(plan, dimension_specs)
    partition_sql = f"PARTITION BY {', '.join(partition)} " if partition else ""
    order_alias = _window_order_alias(dimension_specs)
    direction = plan.order_direction.upper()
    limit = max(1, min(plan.limit or 20, 100))

    if plan.analysis == "year_window_compare":
        months = max(1, min(plan.window_months or 3, 12))
        years = max(1, min(plan.window_years or 3, 10))
        date_column = "sales_date" if metric.table == "fact_sales" else (
            "accounting_month" if metric.table == "fact_policy_monthly" else "reported_date"
        )
        where = [
            *where,
            f"{base_alias}.{date_column} >= date_trunc('month', CURRENT_DATE) - INTERVAL '{years} years'",
            f"{base_alias}.{date_column} < date_trunc('month', CURRENT_DATE)",
            (
                f"EXTRACT(MONTH FROM {base_alias}.{date_column})::int IN ("
                "SELECT EXTRACT(MONTH FROM date_trunc('month', CURRENT_DATE) - "
                f"(n || ' months')::interval)::int FROM generate_series(1, {months}) AS n)"
            ),
        ]
        # Rebuild the aggregate so the seasonal window is part of the grouped query.
        aggregate = (
            "SELECT "
            + ",\n       ".join(select_lines)
            + f"\nFROM {from_sql} {base_alias}"
            + (f"\n{chr(10).join(joins)}" if joins else "")
            + (f"\nWHERE {' AND '.join(where)}" if where else "")
            + (f"\nGROUP BY {group_by}" if group_by else "")
        )

    if plan.analysis == "top_n_per_group":
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
), ranked AS (
  SELECT aggregated.*,
         ROW_NUMBER() OVER ({partition_sql}ORDER BY {metric.alias} {direction}) AS row_number
  FROM aggregated
)
SELECT *
FROM ranked
WHERE row_number <= {limit}
ORDER BY {', '.join([*partition, 'row_number'])}
LIMIT 100""".strip()

    if plan.analysis == "above_average":
        leaf = next(
            (alias for alias in reversed(dimension_aliases) if alias not in partition),
            dimension_aliases[-1],
        )
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
), compared AS (
  SELECT aggregated.*,
         AVG({metric.alias}) OVER ({partition_sql.rstrip()}) AS group_average
  FROM aggregated
)
SELECT *
FROM compared
WHERE {metric.alias} > group_average
ORDER BY {metric.alias} DESC, {leaf}
LIMIT {limit}""".strip()

    if plan.analysis == "period_growth":
        growth_name = "yoy_growth_pct" if plan.time_grain == "year" else "mom_growth_pct"
        lag = f"LAG({metric.alias}) OVER ({partition_sql}ORDER BY {order_alias})"
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
)
SELECT aggregated.*,
       {lag} AS previous_{metric.alias},
       100.0 * ({metric.alias} - {lag}) / NULLIF({lag}, 0) AS {growth_name}
FROM aggregated
ORDER BY {', '.join([*partition, order_alias])}
LIMIT 100""".strip()

    if plan.analysis == "running_total":
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
)
SELECT aggregated.*,
       SUM({metric.alias}) OVER ({partition_sql}ORDER BY {order_alias}
         ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_{metric.alias}
FROM aggregated
ORDER BY {', '.join([*partition, order_alias])}
LIMIT 100""".strip()

    if plan.analysis == "moving_average":
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
)
SELECT aggregated.*,
       AVG({metric.alias}) OVER ({partition_sql}ORDER BY {order_alias}
         ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS moving_average_{metric.alias}
FROM aggregated
ORDER BY {', '.join([*partition, order_alias])}
LIMIT 100""".strip()

    if plan.analysis == "contribution":
        denominator = (
            f"SUM({metric.alias}) OVER (PARTITION BY {', '.join(partition)})"
            if partition
            else f"SUM({metric.alias}) OVER ()"
        )
        return f"""WITH aggregated AS (
  {aggregate.replace(chr(10), chr(10) + '  ')}
)
SELECT aggregated.*,
       100.0 * {metric.alias} / NULLIF({denominator}, 0) AS {metric.alias}_contribution_pct
FROM aggregated
ORDER BY {metric.alias}_contribution_pct DESC
LIMIT {limit}""".strip()

    order = (
        ", ".join(dimension_aliases)
        if plan.intent == "trend" or plan.time_grain
        else f"{metric.alias} {direction}"
    )
    return f"{aggregate}\nORDER BY {order}\nLIMIT {limit}".strip()


def compile_analytical_query(
    plan: QuestionPlan,
    pack: Any | None,
    *,
    force: bool = False,
) -> AnalyticalQuery | None:
    """Compile advanced plans; return ``None`` when legacy/LLM handling is preferable.

    ``force=True`` lets Analytics Builder compile single-dimension breakdowns
    without falling through to narrow legacy templates.
    """
    if pack is None or not plan.dimensions:
        return None
    if not force and not plan.requires_semantic_compiler:
        return None
    metric = _metric_spec(plan)
    dimensions = _dimension_specs(plan, metric.table)
    _validate_specs(pack, metric, dimensions)

    required_tables = {spec.table for spec in dimensions if spec.table != metric.table}
    where = _where_clauses(plan, pack, required_tables)
    joins = _join_clauses(pack, metric.table, required_tables)
    physical_base = getattr(_model_tables(pack)[metric.table], "physical_name", metric.table)
    sql = _render_advanced_sql(
        plan,
        dimensions,
        metric,
        physical_base,
        joins,
        where,
    )
    title = (
        f"{metric.alias.replace('_', ' ').title()} by "
        + ", ".join(spec.alias.replace("_", " ").title() for spec in dimensions)
    )
    return AnalyticalQuery(
        sql=sql,
        title=title,
        dimensions=tuple(spec.alias for spec in dimensions),
        metric=metric.alias,
        required_tables=tuple(sorted({metric.table, *required_tables})),
    )


def expected_dimension_tokens(plan: QuestionPlan) -> dict[str, tuple[str, str]]:
    """Return canonical dimension -> (source column, output alias) for validation."""
    base = "fact_sales" if plan.industry is Industry.AUTOMOTIVE else (
        "fact_policy_monthly"
        if plan.metric in {"premium", "earned_premium", "renewal_rate"}
        else "fact_claims"
    )
    try:
        specs = _dimension_specs(plan, base)
    except SemanticCompileError:
        return {}
    return {spec.key: (spec.column, spec.alias) for spec in specs}
