"""Separately gated post-aggregation SQL with exact structural contracts.

The model sees one governed aggregate relation, never unrestricted warehouse
tables. Supported derived operations are declared, not invented metric formulas.
"""

import json

import sqlglot
from sqlglot import exp

from app.core.exceptions import ValidationError
from app.schemas.bi import BiPanel, BiPlan
from app.services.analytics.bi.llm import BiCompletion, BiProviderError
from app.services.analytics.catalog import Catalog
from app.services.analytics.compiler import BuilderQuery, compile_builder_query

CALCULATIONS = {
    "z_score": "({metric} - AVG({metric}) OVER ()) / NULLIF(STDDEV_POP({metric}) OVER (), 0)",
    "index_to_average": "100.0 * {metric} / NULLIF(AVG({metric}) OVER (), 0)",
}


def shape(panel: BiPanel, catalog: Catalog) -> tuple[BuilderQuery, str, str]:
    if (
        panel.calculation not in CALCULATIONS
        or panel.spec.analysis != "basic"
        or len(panel.spec.dimensions) != 1
        or panel.grain
        or panel.daily
        or panel.spec.dimensions[0] in {"month", "quarter", "year"}
        or panel.kind == "kpi"
    ):
        raise ValidationError(
            "Advanced benchmarking supports one categorical breakdown and standard aggregation."
        )
    source = compile_builder_query(panel.spec, catalog)
    # Remove display truncation BEFORE the benchmark denominator is calculated.
    tree = sqlglot.parse_one(source.sql, read="postgres")
    tree.set("limit", None)
    tree.set("order", None)
    source.sql = tree.sql(dialect="postgres")
    expression = CALCULATIONS[panel.calculation].format(metric=source.metric_column)
    expected = f"SELECT *, {expression} AS bi_value FROM bi_input ORDER BY bi_value DESC NULLS LAST LIMIT {panel.spec.limit}"  # noqa: S608 - closed formulas, catalog identifiers, bounded integer
    return source, expected, expression


def validate_sql(sql: str, expected: str) -> str:
    """Parse *every* statement; AST equality also enforces formula and intent.

    This deliberately supports a closed set of analytical shapes rather than
    claiming a blacklist makes arbitrary LLM SQL safe.
    """
    if len(sql) > 12000:
        raise ValidationError("Advanced SQL exceeds its size budget.")
    try:
        statements = sqlglot.parse(sql, read="postgres")
        allowed = sqlglot.parse_one(expected, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise ValidationError("Advanced SQL could not be parsed.") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise ValidationError("Advanced analysis requires exactly one SELECT.")
    tree = statements[0]
    if tree != allowed:
        raise ValidationError(
            "Advanced SQL changed the approved formula, source, scope or output shape."
        )
    return tree.sql(dialect="postgres")


async def prepare(
    plan: BiPlan, catalog: Catalog, llm: BiCompletion, enabled: bool, prior: dict[str, str]
) -> dict[str, str]:
    panels = [p for p in plan.panels if p.calculation]
    if len(panels) > 1:
        raise ValidationError("Use at most one advanced benchmark per report.")
    if panels and not enabled:
        raise ValidationError(
            "Advanced benchmarking is disabled. Standard trends, rankings and comparisons remain available."
        )
    result = {}
    for panel in panels:
        _, expected, _ = shape(panel, catalog)
        previous = prior.get(panel.id)
        if previous:
            try:
                result[panel.id] = validate_sql(previous, expected)
                continue
            except ValidationError:
                pass
        # One additional call only: shared three-call ceiling prevents panel loops.
        raw = await llm.call(
            "Return JSON with a single sql string. Generate the exact governed PostgreSQL benchmark query requested. Preserve every expression, alias, order and limit. No other statements or tables.",
            json.dumps({"approved_query": expected}),
            max_tokens=600,
        )
        try:
            proposal = json.loads(raw)
            if (
                not isinstance(proposal, dict)
                or set(proposal) != {"sql"}
                or not isinstance(proposal["sql"], str)
            ):
                raise ValueError("Invalid SQL contract")
            result[panel.id] = validate_sql(proposal["sql"], expected)
        except (ValueError, ValidationError) as exc:
            raise BiProviderError(
                "invalid_sql",
                "The advanced query failed structural validation. No query was executed; your report is unchanged.",
            ) from exc
    return result


def compile_advanced(panel: BiPanel, catalog: Catalog, sql: str) -> BuilderQuery:
    source, expected, _ = shape(panel, catalog)
    outer = validate_sql(sql, expected)
    source.sql = f"WITH bi_input AS ({source.sql}) {outer}"
    source.value_column = "bi_value"
    source.metric_format = "decimal"
    source.title = f"{panel.title} ({panel.calculation})"
    source.notes.append(
        "Benchmark is across all matching authorized groups before the display limit; it is descriptive, not causal."
    )
    source.notes.append(
        "Zero or missing reference dispersion/average produces an unavailable benchmark, not zero."
    )
    return source
