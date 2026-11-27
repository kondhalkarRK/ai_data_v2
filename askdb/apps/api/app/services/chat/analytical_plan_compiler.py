# ruff: noqa: S608
# Identifiers are validated semantic/output names; values use SQLGlot literals.
"""Compile a reviewed analytical DAG into ONE governed, scoped read-only statement.

The existing aggregate builder owns formulas, physical columns, joins and filters.
Intermediate values stay in CTE relations; no result-derived SQL interpolation or
model call occurs. Display limits are applied only at the final envelope, after
selection and independent reconciliation across all eligible groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import sqlglot
from sqlglot import exp

from app.analytics.sql_guardrails import sql_is_safe
from app.services.chat.analytical_plan import AnalyticalPlan
from app.services.chat.analytical_plan_validation import (
    CompletenessSource,
    PlanReviewContext,
    review_plan,
)
from app.services.chat.request_capabilities import TypedCompileError
from app.services.chat.request_compiler import _Builder, ident, literal
from app.services.chat.request_contract import RequestedFilter
from app.services.chat.request_dates import comparison_ranges, resolve_period

_INTERVAL = {
    "day": "1 day",
    "week": "7 days",
    "month": "1 month",
    "quarter": "3 months",
    "year": "1 year",
}
_TYPES = {
    "decimal": "NUMERIC",
    "integer": "BIGINT",
    "string": "TEXT",
    "date": "DATE",
    "boolean": "BOOLEAN",
}


@dataclass(frozen=True)
class CompiledAnalysis:
    sql: str
    plan: AnalyticalPlan
    display_limit: int
    checks: tuple[tuple[str, str, str], ...]
    completeness_sources: tuple[CompletenessSource, ...] = ()


def _sql(expression):
    return expression.sql(dialect="postgres")


class _PlanAggregate(_Builder):
    def group_expression(self, field_id, source):
        if field_id == self.date_field and self.request.time_grain:
            grain = self.request.time_grain
            if grain not in _INTERVAL:
                raise TypedCompileError("This dependent plan needs a supported calendar grain")
            return f"date_trunc('{grain}', {self.expression(field_id, source)})::date"
        return super().group_expression(field_id, source)


def _aggregate(
    builder,
    period,
    *,
    period_source=None,
    baseline=False,
    bound_field=None,
    bound_columns=None,
    source_grain=None,
    baseline_kind=None,
    entity_bindings=(),
):
    # not_null introduces the approved binding join path without changing the
    # requested grouping. A NULL selected identity is blocked rather than guessed.
    for _, binding, _ in entity_bindings:
        builder.filters.append(RequestedFilter(field=binding.target_field, operator="not_null"))
    mids = [m.id for m in builder.request.measures]
    query, _ = builder.aggregate("fact_sales", mids, period)
    tree = sqlglot.parse_one(query, read="postgres")
    if period_source:
        if bound_field != builder.date_field or not period.start or not period.end:
            raise TypedCompileError(
                "A period binding requires the approved fact date and a bounded search window"
            )
        parts = (
            list(tree.args["where"].this.flatten())
            if isinstance(tree.args["where"].this, exp.And)
            else [tree.args["where"].this]
        )
        date_sql = builder.expression(builder.date_field, "fact_sales")
        expected = [
            sqlglot.parse_one(f"{date_sql} >= DATE '{period.start}'", read="postgres"),
            sqlglot.parse_one(f"{date_sql} < DATE '{period.end}'", read="postgres"),
        ]
        if len(parts) < 2 or [_sql(p) for p in parts[-2:]] != [_sql(p) for p in expected]:
            raise TypedCompileError(
                "Generated period predicates do not match the approved search window"
            )
        start, end = (f"bp.{ident(c)}" for c in bound_columns)
        shift = ""
        if baseline:
            interval = (
                "1 year"
                if baseline_kind == "same_period_last_year"
                else _INTERVAL.get(source_grain)
            )
            if not interval:
                raise TypedCompileError(
                    "Bound baseline needs a supported equivalent calendar period"
                )
            shift = f" - INTERVAL '{interval}'"
        predicates = [
            *parts[:-2],
            sqlglot.parse_one(f"{date_sql} >= ({start}{shift})::date", read="postgres"),
            sqlglot.parse_one(f"{date_sql} < ({end}{shift})::date", read="postgres"),
        ]
        tree.set("where", exp.Where(this=exp.and_(*predicates)))
        tree.join(f"{period_source} AS bp", join_type="CROSS", copy=False)
        for value, alias in [(start, "__bound_start"), (end, "__bound_end")]:
            tree.select(f"{value} AS {alias}", append=True, copy=False)
            tree.group_by(value, append=True, copy=False)
    for relation, binding, gate in entity_bindings:
        value = builder.expression(binding.target_field, "fact_sales")
        predicate = sqlglot.parse_one(
            f"EXISTS (SELECT 1 FROM {relation} ev WHERE {value} IS NOT DISTINCT FROM ev.{ident(binding.source_columns[0])}) AND ({gate})",
            read="postgres",
        )
        tree.where(predicate, append=True, copy=False)
    return _sql(tree)


def compile_analysis(
    plan: AnalyticalPlan, review: PlanReviewContext, *, today: date, display_limit: int = 50
) -> CompiledAnalysis:
    result = review_plan(plan, review)
    if result.status != "valid":
        raise TypedCompileError(
            "; ".join(i.message for i in result.issues)
            or "Plan is not fully verified for compilation"
        )
    plan = AnalyticalPlan.model_validate_json(plan.model_dump_json())
    if not 1 <= display_limit <= 50:
        raise TypedCompileError("Dependent display limit must be within 1..50 per step")
    if any(
        s.request.windows or s.request.operations or s.request.measure_filters for s in plan.steps
    ):
        raise TypedCompileError(
            "This dependent operation combination is not registered; the ordinary compiler still supports its existing windows/operations"
        )
    ctes, relations, stats, bound_keys = [], {}, {}, {}
    by_id = {s.id: s for s in plan.steps}
    for index, step in enumerate(plan.steps):
        base = f"ap_{index}"
        all_rows, relation = base + "_all", base + "_rows"
        relations[step.id], stats[step.id] = relation, base + "_stats"
        if step.input_step:
            source = by_id[step.input_step]
            rank = step.request.ranking
            output = next(
                (
                    o.name
                    for o in source.outputs
                    if o.semantic_id == rank.measure_id
                    and o.role
                    == {
                        "value": "value",
                        "absolute_change": "change",
                        "percent_change": "percent_change",
                    }[rank.basis]
                ),
                None,
            )
            if output is None:
                raise TypedCompileError("Selection ranking output is unavailable")
            ctes.append(
                f"{base}_rank AS (SELECT s.*, RANK() OVER (ORDER BY s.{ident(output)} {rank.direction.upper()}) AS __selection_rank FROM {relations[source.id]} s WHERE s.{ident(output)} IS NOT NULL)"
            )
            projection = []
            source_outputs = {(o.role, o.semantic_id): o.name for o in source.outputs}
            for out in step.outputs:
                value = (
                    "__selection_rank"
                    if out.role == "rank"
                    else ident(source_outputs[(out.role, out.semantic_id)])
                )
                projection.append(f"{value} AS {ident(out.name)}")
            query = f"SELECT {', '.join(projection)} FROM {base}_rank WHERE __selection_rank <= {rank.limit}"
            bound_keys[step.id] = False
        else:
            req = step.request.model_copy(
                deep=True, update={"outcome": "analytics", "ranking": None}
            )
            builder = _PlanAggregate(review.pack, req, review.context, review.principal, today)
            if any(
                review.pack.model.measures[m.id].source_table != "fact_sales" for m in req.measures
            ):
                raise TypedCompileError(
                    "Dependent execution currently requires a registered fact_sales plan"
                )
            period_binding = next((b for b in step.bindings if b.kind == "period"), None)
            if sum(b.kind == "period" for b in step.bindings) > 1:
                raise TypedCompileError("Multiple selected period axes need an aligned plan")
            entity_bindings = []
            for b in step.bindings:
                if b.kind == "entity_set":
                    src = relations[b.source_step]
                    entity_bindings.append(
                        (
                            src,
                            b,
                            f"(SELECT COUNT(*) FROM {src}) <= {b.max_items} AND NOT EXISTS (SELECT 1 FROM {src} WHERE {ident(b.source_columns[0])} IS NULL)",
                        )
                    )
            common = {"entity_bindings": entity_bindings}
            if period_binding:
                src_step = by_id[period_binding.source_step]
                if src_step.request.group_by:
                    raise TypedCompileError(
                        "A bound period must be selected independently of other dimensions"
                    )
                common.update(
                    period_source=relations[period_binding.source_step],
                    bound_field=period_binding.target_field,
                    bound_columns=period_binding.source_columns,
                    source_grain=src_step.request.time_grain,
                    baseline_kind=step.baseline.kind if step.baseline else None,
                )
                current = resolve_period(req.period, today, builder.policy)
                baseline = current  # The SQL binding supplies the actual shifted bounds.
            elif step.baseline:
                current, baseline = comparison_ranges(
                    req.comparisons[0], req.period, today, builder.policy
                )
            else:
                current = resolve_period(req.period, today, builder.policy)
                baseline = None
            if current.start is None or current.end is None:
                raise TypedCompileError("Dependent analysis requires an explicit bounded period")
            if req.time_grain and step.baseline:
                raise TypedCompileError(
                    "Time-grain comparison requires a registered aligned dependent operation"
                )
            current_sql = _aggregate(builder, current, **common)
            ctes.append(f"{base}_current AS ({current_sql})")
            keys = list(builder.aliases.values()) + (
                ["__bound_start", "__bound_end"] if period_binding else []
            )
            bound_keys[step.id] = bool(period_binding)
            if step.baseline:
                # Rebuild to avoid accumulating synthetic join-discovery filters.
                other = _PlanAggregate(review.pack, req, review.context, review.principal, today)
                baseline_sql = _aggregate(other, baseline, baseline=True, **common)
                ctes.append(f"{base}_baseline AS ({baseline_sql})")
                joins = " AND ".join(f"c.{k} IS NOT DISTINCT FROM b.{k}" for k in keys) or "TRUE"
                expressions = {
                    ("dimension", f): f"COALESCE(c.{a}, b.{a})" for f, a in builder.aliases.items()
                }
                for measure in req.measures:
                    mid = ident(measure.id)
                    expressions.update(
                        {
                            ("current", mid): f"c.{mid}",
                            ("baseline", mid): f"b.{mid}",
                            ("change", mid): f"c.{mid} - b.{mid}",
                            (
                                "percent_change",
                                mid,
                            ): f"100.0 * (c.{mid} - b.{mid}) / NULLIF(ABS(b.{mid}), 0)",
                        }
                    )
                projection = [
                    _projection(
                        o, expressions, builder, prefix="c", period_bound=bool(period_binding)
                    )
                    for o in step.outputs
                ]
                if period_binding:
                    projection += [
                        f"COALESCE(c.{k}, b.{k}) AS {k}" for k in ("__bound_start", "__bound_end")
                    ]
                query = f"SELECT {', '.join(projection)} FROM {base}_current c FULL OUTER JOIN {base}_baseline b ON {joins}"
            else:
                expressions = {("dimension", f): f"c.{a}" for f, a in builder.aliases.items()}
                expressions.update({("value", m.id): f"c.{ident(m.id)}" for m in req.measures})
                projection = [
                    _projection(
                        o, expressions, builder, prefix="c", period_bound=bool(period_binding)
                    )
                    for o in step.outputs
                ]
                if period_binding:
                    projection += [f"c.{k} AS {k}" for k in ("__bound_start", "__bound_end")]
                query = f"SELECT {', '.join(projection)} FROM {base}_current c"
            # Entity and period bindings both gate execution of later CTE branches.
            gates = []
            for b in step.bindings:
                src = relations[b.source_step]
                gates += [
                    f"EXISTS (SELECT 1 FROM {src})",
                    f"(SELECT COUNT(*) FROM {src}) <= {b.max_items}",
                ]
            if gates:
                query = f"SELECT * FROM ({query}) bound WHERE {' AND '.join(gates)}"
            if step.change_conditions:
                predicates = []
                for condition in step.change_conditions:
                    col = next(
                        o.name
                        for o in step.outputs
                        if o.role == condition.basis and o.semantic_id == condition.measure_id
                    )
                    op = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=", "ne": "<>"}[
                        condition.operator
                    ]
                    predicates.append(f"{ident(col)} {op} {literal(condition.value)}")
                query = f"SELECT * FROM ({query}) changes WHERE {' AND '.join(predicates)}"
        ctes.append(f"{all_rows} AS ({query})")
        ctes.append(f"{stats[step.id]} AS (SELECT COUNT(*) AS n FROM {all_rows})")
        gate = "TRUE"
        if step.selection:
            gate = f"(SELECT n FROM {stats[step.id]}) <= {step.selection.cohort_cap}"
        if step.request.ranking and not step.selection:
            ranking = step.request.ranking
            role = {
                "value": "value",
                "absolute_change": "change",
                "percent_change": "percent_change",
            }.get(ranking.basis)
            col = next(
                (
                    o.name
                    for o in step.outputs
                    if o.role == role and o.semantic_id == ranking.measure_id
                ),
                None,
            )
            if col is None or ranking.partition_by or ranking.include_both_ends:
                raise TypedCompileError("This ranking needs a registered dependent operation")
            ctes.append(
                f"{base}_display_rank AS (SELECT *, RANK() OVER (ORDER BY {ident(col)} {ranking.direction.upper()} NULLS LAST) AS __display_rank FROM {all_rows})"
            )
            ctes.append(
                f"{relation} AS (SELECT * FROM {base}_display_rank WHERE __display_rank <= {ranking.limit})"
            )
        else:
            ctes.append(f"{relation} AS (SELECT * FROM {all_rows} WHERE {gate})")

    checks = []
    for i, check in enumerate(plan.reconciliations):
        head = next(j for j, s in enumerate(plan.steps) if s.id == check.headline_step)
        detail = next(j for j, s in enumerate(plan.steps) if s.id == check.contributor_step)
        hstep, dstep = by_id[check.headline_step], by_id[check.contributor_step]
        hcol = {o.role: o.name for o in hstep.outputs if o.semantic_id == check.measure_id}
        dcol = {o.role: o.name for o in dstep.outputs if o.semantic_id == check.measure_id}
        keys = ["__bound_start", "__bound_end"] if bound_keys[dstep.id] else []
        on = " AND ".join(f"h.{k} IS NOT DISTINCT FROM d.{k}" for k in keys) or "TRUE"
        group = ", ".join(keys)
        aggregates = ", ".join(
            f"SUM({ident(dcol[r])}) AS {r}" for r in ("current", "baseline", "change")
        )
        missing = f"SUM(CASE WHEN {ident(dcol['current'])} IS NULL OR {ident(dcol['baseline'])} IS NULL THEN 1 ELSE 0 END) AS missing"
        ctes.append(
            f"ap_check_{i}_detail AS (SELECT {group + ', ' if keys else ''}{aggregates}, {missing} FROM ap_{detail}_all"
            + (f" GROUP BY {group}" if keys else "")
            + ")"
        )
        bad = " OR ".join(
            f"h.{ident(hcol[r])} IS NULL OR d.{r} IS NULL OR ABS(h.{ident(hcol[r])} - d.{r}) > 0.000001"
            for r in ("current", "baseline", "change")
        )
        ctes.append(
            f"ap_check_{i} AS (SELECT COUNT(*) AS bad FROM ap_{head}_all h FULL OUTER JOIN ap_check_{i}_detail d ON {on} WHERE d.missing IS NULL OR d.missing > 0 OR {bad})"
        )
        checks.append((check.headline_step, check.contributor_step, check.measure_id))

    # Stable wide envelope: typed NULLs prevent UNION type coercion from mixing
    # unrelated dates, strings and numbers. Empty steps still have a control row.
    selects = []
    for i, step in enumerate(plan.steps):
        relation = relations[step.id]
        order = _order(step)
        payload = [
            f"{literal(step.id)} AS __step",
            "r.__present",
            f"(SELECT COUNT(*) FROM {relation}) AS __count",
            f"(SELECT n FROM {stats[step.id]}) AS __total",
            "r.__bound_start AS __period_start"
            if bound_keys[step.id]
            else "CAST(NULL AS DATE) AS __period_start",
            "r.__bound_end AS __period_end"
            if bound_keys[step.id]
            else "CAST(NULL AS DATE) AS __period_end",
        ]
        payload += [f"(SELECT bad FROM ap_check_{j}) AS __check_{j}" for j in range(len(checks))]
        for j, other in enumerate(plan.steps):
            for o in other.outputs:
                value = f"r.{ident(o.name)}" if i == j else f"CAST(NULL AS {_TYPES[o.value_type]})"
                payload.append(f"{value} AS s{j}_{ident(o.name)}")
        selects.append(
            f"SELECT {', '.join(payload)} FROM (SELECT 1) control LEFT JOIN (SELECT *, ROW_NUMBER() OVER (ORDER BY {order}) AS __present FROM {relation} ORDER BY {order} LIMIT {display_limit}) r ON TRUE"
        )
    sql = f"WITH {', '.join(ctes)} {' UNION ALL '.join(selects)} LIMIT {display_limit * len(plan.steps)}"
    safe, reason = sql_is_safe(sql)
    if not safe:
        raise TypedCompileError(reason)
    tree = sqlglot.parse_one(sql, read="postgres")
    allowed = {t.physical_name for t in review.pack.model.tables.values()}
    aliases = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        physical = f"{table.db}.{table.name}" if table.db else table.name
        if physical not in allowed and physical not in aliases:
            raise TypedCompileError("Composite SQL references an unapproved source")
    return CompiledAnalysis(sql, plan, display_limit, tuple(checks), review.completeness_sources)


def _projection(output, expressions, builder, *, prefix, period_bound):
    if output.role in {"period_start", "period_end"}:
        if period_bound:
            value = (
                f"COALESCE(c.__bound_{'start' if output.role == 'period_start' else 'end'}, b.__bound_{'start' if output.role == 'period_start' else 'end'})"
                if builder.request.comparisons
                else f"{prefix}.__bound_{'start' if output.role == 'period_start' else 'end'}"
            )
        else:
            alias = builder.aliases.get(output.semantic_id)
            if not alias or builder.request.time_grain not in _INTERVAL:
                raise TypedCompileError("A period output needs an actual calendar grouping")
            value = f"{prefix}.{ident(alias)}"
            if output.role == "period_end":
                value = f"({value} + INTERVAL '{_INTERVAL[builder.request.time_grain]}')::date"
    else:
        value = expressions.get((output.role, output.semantic_id))
        if value is None:
            raise TypedCompileError("An output operation has no registered SQL projection")
    return f"{value} AS {ident(output.name)}"


def _order(step):
    if step.request.ranking:
        rank = step.request.ranking
        role = {
            "value": "value",
            "absolute_change": "change",
            "percent_change": "percent_change",
        }.get(rank.basis)
        col = next(
            (o.name for o in step.outputs if o.role == role and o.semantic_id == rank.measure_id),
            None,
        )
        if not col:
            raise TypedCompileError("Ranking output is absent")
        return f"{ident(col)} {rank.direction.upper()} NULLS LAST, " + ", ".join(
            ident(o.name) for o in step.outputs
        )
    return ", ".join(ident(o.name) for o in step.outputs)
