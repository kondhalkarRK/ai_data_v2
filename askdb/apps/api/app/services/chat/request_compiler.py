# ruff: noqa: S608
# SQL identifiers come from validated semantic metadata; values use SQLGlot literals.
"""Typed request -> governed PostgreSQL. No question parsing and no LLM SQL path.

Reuses the semantic compiler's join discovery and period labels. Base formulas
come exclusively from the validated pack. Multi-fact measures aggregate BEFORE
combining; unsupported grains produce an explicit partial/unsupported outcome.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import sqlglot
from sqlglot import exp

from app.analytics.sql_guardrails import sql_is_safe
from app.core.config import Industry
from app.schemas.semantic import SemanticPackResponse
from app.services.chat.period_labels import period_label_sql
from app.services.chat.question_understanding import QuestionPlan
from app.services.chat.request_capabilities import (
    TypedCompileError,
    approved_formula,
    measure_capabilities,
)
from app.services.chat.request_context import RequestContext, RequestPrincipal, pack_fingerprint
from app.services.chat.request_contract import InterpretedRequest, RequestedFilter
from app.services.chat.request_dates import (
    DateRange,
    RequestClarificationError,
    comparison_ranges,
    resolve_period,
)
from app.services.chat.request_interpreter import validate_proposal
from app.services.chat.semantic_analytics import _ALIASES, _join_clauses, _relationship_path


def ident(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9]*", value):
        raise TypedCompileError("Semantic identifiers must be simple identifiers")
    return value


def literal(value: Any) -> str:
    return exp.convert(value).sql(dialect="postgres")


@dataclass
class CompiledRequest:
    sql: str
    request: InterpretedRequest
    columns: list[str]
    group_aliases: dict[str, str]
    notes: list[str] = field(default_factory=list)
    unsupported: dict[str, str] = field(default_factory=dict)
    periods: dict[str, DateRange] = field(default_factory=dict)
    total_groups: int | None = None
    coverage_columns: dict[str, tuple[str, str, str]] = field(default_factory=dict)


class _Builder:
    def __init__(self, pack, request, context, principal, today):
        self.pack, self.request, self.context, self.principal, self.today = (
            pack,
            request,
            context,
            principal,
            today,
        )
        self.policy = pack.model.query_policy
        if self.policy is None:
            raise TypedCompileError("No approved typed-query policy exists for this pack")
        self.entities = {e["id"]: e for e in context.payload["entities"]}
        self.groups = list(dict.fromkeys(request.group_by))
        self.filters = list(request.filters)
        self.notes: list[str] = []
        self.unsupported: dict[str, str] = {}
        self.ctes: list[str] = []
        self.periods: dict[str, DateRange] = {}
        self.coverage_sources: list[tuple[str, str, str]] = []
        self.capabilities = measure_capabilities(pack)
        self.date_field = next(
            (
                f
                for f, spec in context.payload["fields"].items()
                if spec["type"] == "date" and f.startswith("fact_")
            ),
            "fact_sales.sales_date",
        )
        self.needs_index = any(
            w.operation != "contribution" or w.reset not in {"none", "unspecified"}
            for w in request.windows
        )
        self.member_entities = []
        made_values = {
            str(self.entities[key]["value"])
            for f in request.filters
            if f.field == "dim_carline.make" and f.operator in {"eq", "in"}
            for key in f.entity_ids
        }
        made_values.update(
            str(v)
            for f in request.filters
            if f.field == "dim_carline.make" and f.operator in {"eq", "in"}
            for v in f.values
        )
        referenced = (
            set(request.entity_ids)
            | {key for f in request.filters for key in f.entity_ids}
            | {key for c in request.comparisons for key in c.member_ids}
        )
        for key in referenced:
            entity = self.entities[key]
            makes = set(entity.get("makes", []))
            if made_values:
                makes &= made_values
            if len(makes) > 1 and "dim_carline.make" not in self.groups:
                raise RequestClarificationError(f"Which make should I use for {entity['value']}?")
        if sum(c.kind == "members" for c in request.comparisons) > 1:
            raise TypedCompileError(
                "Multiple member-comparison axes require a dedicated aligned plan"
            )
        for comp in request.comparisons:
            if comp.kind == "members":
                members = [self.entities[key] for key in comp.member_ids]
                if len({e["field"] for e in members}) != 1:
                    raise TypedCompileError("Comparison members must belong to the same dimension")
                member_field = members[0]["field"]
                self.member_entities = members
                if member_field not in self.groups:
                    self.groups.append(member_field)
                self.filters.append(
                    RequestedFilter(field=member_field, operator="in", entity_ids=comp.member_ids)
                )
        used = {key for f in self.filters for key in f.entity_ids}
        if not set(request.entity_ids) <= used:
            raise TypedCompileError(
                "Each entity restriction must be represented by an explicit filter/comparison"
            )
        if request.time_grain and self.date_field not in self.groups:
            self.groups.insert(0, self.date_field)
        names = [f.split(".")[-1] for f in self.groups]
        self.aliases = {
            f: (
                request.time_grain
                if f == self.date_field and request.time_grain
                else (
                    f.replace(".", "__") if names.count(f.split(".")[-1]) > 1 else f.split(".")[-1]
                )
            )
            for f in self.groups
        }

    def mapped(self, field_id: str, source: str) -> tuple[str, str]:
        if source == "dim_targets":
            field_id = self.policy.equivalent_dimensions.get(field_id, field_id)
        table, column = field_id.split(".")
        if (
            table not in self.pack.model.tables
            or column not in self.pack.model.tables[table].columns
        ):
            raise TypedCompileError(f"Unsupported field {field_id}")
        if source == "dim_targets" and table != source:
            raise TypedCompileError("Targets cannot be allocated to this filter/grouping")
        return table, column

    def expression(self, field_id: str, source: str) -> str:
        table, column = self.mapped(field_id, source)
        alias = _ALIASES.get(table)
        if alias is None:
            raise TypedCompileError("No approved table alias/plan for this source")
        return f"{ident(alias)}.{ident(column)}"

    def group_expression(self, field_id: str, source: str) -> str:
        value = self.expression(field_id, source)
        if field_id == self.date_field and self.request.time_grain:
            grain = self.request.time_grain
            if grain in {"month", "quarter", "half"}:
                return period_label_sql(value, grain)
            if grain == "year":
                return f"EXTRACT(YEAR FROM {value})::int"
            if grain in {"day", "week"}:
                return f"date_trunc('{grain}', {value})::date"
        return value

    def predicate(self, filt: RequestedFilter, source: str) -> str:
        column = self.expression(filt.field, source)
        values = (
            [self.entities[key]["value"] for key in filt.entity_ids]
            if filt.entity_ids
            else filt.values
        )
        if filt.operator in {"is_null", "not_null"}:
            return f"{column} IS {'NOT ' if filt.operator == 'not_null' else ''}NULL"
        if filt.operator in {"in", "not_in"}:
            return f"{column} {'NOT IN' if filt.operator == 'not_in' else 'IN'} ({', '.join(literal(v) for v in values)})"
        operator = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[
            filt.operator
        ]
        return f"{column} {operator} {literal(values[0])}"

    def aggregate(
        self, source: str, measures: list[str], period: DateRange
    ) -> tuple[str, list[str]]:
        if source == "dim_targets":
            if self.principal.scope.restricted:
                raise TypedCompileError("Regional target allocation is not defined")
            if self.request.time_grain in {"day", "week"}:
                raise TypedCompileError("Monthly targets cannot be allocated to days or weeks")
            self.notes.append(
                "Targets retain their full monthly planned values; no daily/region/model allocation is inferred."
            )
        if source not in _ALIASES:
            raise TypedCompileError("This fact needs an approved source plan")
        fields = self.groups + [f.field for f in self.filters]
        tables = {self.mapped(f, source)[0] for f in fields}
        for table in tables - {source}:
            node = source
            for relationship in _relationship_path(self.pack, source, table):
                if relationship.from_table != node or relationship.type not in {
                    "many_to_one",
                    "one_to_one",
                }:
                    raise TypedCompileError("Join would cross an unapproved grain/cardinality")
                if (
                    relationship.to_column
                    != self.pack.model.tables[relationship.to_table].primary_key
                ):
                    raise TypedCompileError("Join target is not the declared primary key")
                node = relationship.to_table
        projection = QuestionPlan(
            industry=Industry.AUTOMOTIVE,
            intent="aggregation",
            entity="dealer" if any(f.startswith("dim_dealer.") for f in fields) else "metric_only",
            metric="revenue",
            dimensions=[f.split(".")[-1] for f in self.groups],
        )
        joins = ["LEFT " + join for join in _join_clauses(self.pack, source, tables, projection)]
        # Validate the joins actually emitted, including the dealer-home-region path.
        alias_tables = {alias: table for table, alias in _ALIASES.items()}
        for join in joins:
            parsed = sqlglot.parse_one(
                f"SELECT 1 FROM {self.pack.model.tables[source].physical_name} {_ALIASES[source]} {join}",
                read="postgres",
            )
            condition = next(parsed.find_all(exp.Join)).args.get("on")
            if (
                not isinstance(condition, exp.EQ)
                or not isinstance(condition.this, exp.Column)
                or not isinstance(condition.expression, exp.Column)
            ):
                raise TypedCompileError("Join needs a declared key equality")
            pair = {
                (alias_tables.get(c.table), c.name) for c in (condition.this, condition.expression)
            }
            if not any(
                pair == {(r.from_table, r.from_column), (r.to_table, r.to_column)}
                and r.type in {"many_to_one", "one_to_one"}
                and r.auto_join
                and not r.join_condition
                and r.to_column == self.pack.model.tables[r.to_table].primary_key
                for r in self.pack.model.relationships
            ):
                raise TypedCompileError(
                    "Emitted join is not an approved key/cardinality relationship"
                )
        dims = [self.group_expression(f, source) for f in self.groups]
        selections = [
            f"{value} AS {ident(self.aliases[key])}"
            for key, value in zip(self.groups, dims, strict=True)
        ]
        aliases = []
        if self.needs_index:
            value = self.expression(self.date_field, source)
            grain = self.request.time_grain
            index = f"EXTRACT(YEAR FROM {value})::int"
            if grain in {"month", "quarter"}:
                month = f"EXTRACT(MONTH FROM {value})::int"
                index = (
                    f"({index} * 12 + {month} - 1)"
                    if grain == "month"
                    else f"({index} * 4 + FLOOR(({month} - 1) / 3.0))"
                )
            elif grain in {"day", "week"}:
                index = f"FLOOR(EXTRACT(EPOCH FROM date_trunc('{grain}', {value})) / {86400 if grain == 'day' else 604800})"
            selections.append(f"MIN({index}) AS __period_index")
        for measure_id in measures:
            tree = approved_formula(self.pack, measure_id).copy()
            for column in tree.find_all(exp.Column):
                column.set("table", exp.to_identifier(_ALIASES[source]))
            selections.append(f"{tree.sql(dialect='postgres')} AS {ident(measure_id)}")
            aliases.append(measure_id)
        predicates = [self.predicate(f, source) for f in self.filters]
        date_column = self.expression(self.date_field, source)
        selections += [
            f"MIN({date_column}) AS __coverage_start",
            f"MAX({date_column}) AS __coverage_through",
        ]
        if period.start:
            predicates.append(f"{date_column} >= DATE '{period.start.isoformat()}'")
        if period.end:
            predicates.append(f"{date_column} < DATE '{period.end.isoformat()}'")
        sql = f"SELECT {', '.join(selections)} FROM {self.pack.model.tables[source].physical_name} {_ALIASES[source]}"
        sql += " " + " ".join(joins)
        if predicates:
            sql += " WHERE " + " AND ".join(predicates)
        if dims:
            sql += " GROUP BY " + ", ".join(dims)
        # Empty source is no matching data, not an invented scalar zero.
        sql += " HAVING COUNT(*) > 0"
        return sql, aliases

    def combined(self, period: DateRange, prefix: str) -> tuple[str, list[str]]:
        by_source: dict[str, list[str]] = defaultdict(list)
        for measure in self.request.measures:
            capability = self.capabilities[measure.id]
            if capability["status"] == "definition_only":
                self.unsupported[measure.id] = capability["reason"]
                continue
            by_source[self.pack.model.measures[measure.id].source_table].append(measure.id)
        sources = []
        columns = []
        for index, (source, measures) in enumerate(by_source.items()):
            try:
                sql, aliases = self.aggregate(source, measures, period)
            except (TypedCompileError, ValueError) as exc:
                self.unsupported.update(dict.fromkeys(measures, str(exc)))
                continue
            name = f"{prefix}_{index}"
            self.ctes.append(f"{name} AS ({sql})")
            self.coverage_sources.append((prefix, source, name))
            sources.append((name, aliases))
            columns += aliases
        if not sources:
            raise TypedCompileError(
                "; ".join(self.unsupported.values()) or "No executable measures"
            )
        output = []
        for key in self.aliases.values():
            output.append(
                f"COALESCE({', '.join(f'{name}.{key}' for name, _ in sources)}) AS {key}"
                if len(sources) > 1
                else f"{sources[0][0]}.{key} AS {key}"
            )
        if self.needs_index:
            output.append(
                f"COALESCE({', '.join(name + '.__period_index' for name, _ in sources)}) AS __period_index"
                if len(sources) > 1
                else f"{sources[0][0]}.__period_index AS __period_index"
            )
        for name, aliases in sources:
            output += [f"{name}.{key} AS {key}" for key in aliases]
        joined = sources[0][0]
        prior = [sources[0][0]]
        for name, _ in sources[1:]:
            condition = (
                " AND ".join(
                    f"{name}.{key} IS NOT DISTINCT FROM "
                    + (
                        f"COALESCE({', '.join(p + '.' + key for p in prior)})"
                        if len(prior) > 1
                        else f"{prior[0]}.{key}"
                    )
                    for key in self.aliases.values()
                )
                or "TRUE"
            )
            joined += f" FULL OUTER JOIN {name} ON {condition}"
            prior.append(name)
        name = prefix + "_combined"
        self.ctes.append(f"{name} AS (SELECT {', '.join(output)} FROM {joined})")
        return name, columns

    def build(self, limit: int) -> CompiledRequest:
        req = self.request
        if req.outcome != "analytics" or req.clarification:
            raise TypedCompileError("This outcome is not an executable analytical request")
        if any(c.kind == "benchmark" for c in req.comparisons):
            raise TypedCompileError("Benchmark comparison needs an approved benchmark plan")
        target_comparisons = [c for c in req.comparisons if c.kind == "actual_target"]
        if target_comparisons and (
            req.windows or req.operations or any(c.kind == "period" for c in req.comparisons)
        ):
            raise TypedCompileError(
                "Actual/target with other transformations requires a dedicated plan"
            )
        period_comparisons = [c for c in req.comparisons if c.kind == "period"]
        if len(period_comparisons) > 1 or (period_comparisons and (req.time_grain or req.windows)):
            raise TypedCompileError(
                "Multiple/time-grain comparison baselines require a dedicated aligned plan"
            )
        if req.period is None and not period_comparisons:
            if not req.ranking:
                raise RequestClarificationError("Which date range should I use?")
            period = DateRange(
                None, self.today + timedelta(days=1), "Available history through today", True
            )
            self.notes.append(
                "Undated ranking uses available history within your permitted scope, through today."
            )
        else:
            period = resolve_period(req.period, self.today, self.policy) if req.period else None
        if period_comparisons:
            current, baseline = comparison_ranges(
                period_comparisons[0], req.period, self.today, self.policy
            )
            self.periods = {"current": current, "baseline": baseline}
            c, cols = self.combined(current, "current")
            b, previous_cols = self.combined(baseline, "baseline")
            if cols != previous_cols:
                raise TypedCompileError("Comparison measure coverage differs between periods")
            selections = [f"COALESCE(c.{key}, b.{key}) AS {key}" for key in self.aliases.values()]
            output_cols = []
            for key in cols:
                selections += [
                    f"c.{key} AS current_{key}",
                    f"b.{key} AS baseline_{key}",
                    f"c.{key} - b.{key} AS change_{key}",
                    f"100.0 * (c.{key} - b.{key}) / NULLIF(ABS(b.{key}), 0) AS {key}_change_pct",
                ]
                output_cols += [
                    f"current_{key}",
                    f"baseline_{key}",
                    f"change_{key}",
                    f"{key}_change_pct",
                ]
            on = (
                " AND ".join(
                    f"c.{key} IS NOT DISTINCT FROM b.{key}" for key in self.aliases.values()
                )
                or "TRUE"
            )
            self.ctes.append(
                f"results AS (SELECT {', '.join(selections)} FROM {c} c FULL OUTER JOIN {b} b ON {on})"
            )
            columns = output_cols
            self.notes.append(
                "Comparison shows both periods; missing observations remain unavailable. Percent change uses absolute baseline and is unavailable for zero baseline."
            )
        else:
            assert period is not None
            self.periods = {"selection": period}
            name, columns = self.combined(period, "selected")
            self.ctes.append(
                f"results AS (SELECT {', '.join([*self.aliases.values(), *columns, *(['__period_index'] if self.needs_index else [])])} FROM {name})"
            )
        base = "results"
        if target_comparisons:
            pairs = [
                (actual, target)
                for actual, target in (
                    ("revenue", "target_revenue"),
                    ("units_sold", "target_units"),
                )
                if actual in columns and target in columns
            ]
            if not pairs:
                self.notes.append(
                    "Actual versus target is unavailable at this scope; only supported measures are returned."
                )
            else:
                additions = []
                for actual, target in pairs:
                    additions += [
                        f"{actual} - {target} AS {actual}_target_variance",
                        f"100.0 * {actual} / NULLIF({target}, 0) AS {actual}_attainment_pct",
                    ]
                    columns += [f"{actual}_target_variance", f"{actual}_attainment_pct"]
                self.ctes.append(
                    f"target_results AS (SELECT *, {', '.join(additions)} FROM results)"
                )
                base = "target_results"
        # Keep comparison members even when one has no records. Never synthesize zero.
        if self.member_entities and not period_comparisons:
            member_field = self.member_entities[0]["field"]
            key = self.aliases[member_field]
            other = [k for k in self.aliases.values() if k != key]
            members = " UNION ALL ".join(
                f"SELECT {literal(e['value'])} AS {key}" for e in self.member_entities
            )
            self.ctes.append(f"members AS ({members})")
            source = "members m"
            if other:
                self.ctes.append(
                    f"axes AS (SELECT DISTINCT {', '.join([*other, *(['__period_index'] if self.needs_index else [])])} FROM results)"
                )
                source += " CROSS JOIN axes a"
            on = f"r.{key} = m.{key}" + "".join(
                f" AND r.{c} IS NOT DISTINCT FROM a.{c}" for c in other
            )
            select = [
                f"m.{key} AS {key}",
                *(f"a.{c} AS {c}" for c in other),
                *(f"r.{c} AS {c}" for c in columns),
                *(["a.__period_index AS __period_index"] if self.needs_index and other else []),
            ]
            self.ctes.append(
                f"member_results AS (SELECT {', '.join(select)} FROM {source} LEFT JOIN results r ON {on})"
            )
            if target_comparisons:
                raise TypedCompileError(
                    "Member comparison with targets requires an aligned target plan"
                )
            base = "member_results"
        if req.operations:
            if req.windows or period_comparisons:
                raise TypedCompileError(
                    "Post-aggregation with windows/comparisons requires a dedicated plan"
                )
            if len(req.operations) != 1:
                raise TypedCompileError("Only one post-aggregation stage is supported")
            op = req.operations[0]
            if set(op.measure_ids) != {m.id for m in req.measures}:
                raise TypedCompileError("Post-aggregation must account for every requested measure")
            if op.operation == "ratio" or any(
                self.pack.model.measures[m].aggregation == "ratio" for m in op.measure_ids
            ):
                raise TypedCompileError("Post-aggregation ratios require an approved weighted plan")
            group = [self.aliases[f] for f in op.group_by if f in self.aliases]
            if len(group) != len(op.group_by):
                raise TypedCompileError("Post-aggregation grouping must be in the base grouping")
            func = {
                "sum": "SUM",
                "avg": "AVG",
                "min": "MIN",
                "max": "MAX",
                "count": "COUNT",
                "count_distinct": "COUNT",
            }[op.operation]
            exprs = [
                f"{func}({'DISTINCT ' if op.operation == 'count_distinct' else ''}{m}) AS {op.operation}_{m}"
                for m in op.measure_ids
            ]
            self.ctes.append(
                f"post_results AS (SELECT {', '.join([*group, *exprs])} FROM {base}"
                + (" GROUP BY " + ", ".join(group) if group else "")
                + ")"
            )
            base, columns = "post_results", [f"{op.operation}_{m}" for m in op.measure_ids]
            self.aliases = {f: a for f, a in self.aliases.items() if a in group}
        if req.windows:
            if self.needs_index and (
                self.date_field not in self.aliases
                or req.time_grain not in {"month", "quarter", "year", "day", "week"}
            ):
                raise RequestClarificationError(
                    "Which time grain should the window calculation use?"
                )
            additions = []
            for window in req.windows:
                if window.operation != "contribution" and window.order_by != self.date_field:
                    raise TypedCompileError("Time windows must order by the approved date field")
                if any(
                    self.pack.model.measures[m].aggregation == "ratio" for m in window.measure_ids
                ):
                    raise TypedCompileError(
                        "Cumulative/rolling ratios need an approved weighted numerator/denominator plan"
                    )
                if any(m not in columns for m in window.measure_ids):
                    raise TypedCompileError("A window measure is unavailable at this grain")
                parts = window.partition_by
                if window.operation != "contribution":
                    expected = set(self.groups) - {self.date_field}
                    parts = parts or sorted(expected)
                    if set(parts) != expected:
                        raise RequestClarificationError(
                            "Should the window run separately for each grouped series?"
                        )
                if not set(parts) <= set(self.aliases):
                    raise TypedCompileError("Window partitions must be grouped dimensions")
                partition = [self.aliases[f] for f in parts]
                partition_a = [f"a.{key}" for key in partition]
                conditions = [f"b.{key} IS NOT DISTINCT FROM a.{key}" for key in partition]
                if window.reset not in {"none", "unspecified"}:
                    grain = req.time_grain
                    if grain not in {"month", "quarter", "year"}:
                        raise TypedCompileError(
                            "Daily/weekly reset windows need an approved calendar bucket plan"
                        )
                    divisor = (
                        1
                        if window.reset == "quarter" and grain == "quarter"
                        else 3
                        if window.reset == "quarter" and grain == "month"
                        else {"month": 12, "quarter": 4, "year": 1}[grain]
                    )
                    offset = (
                        (self.policy.fiscal_year_start_month - 1)
                        if window.reset == "fiscal_year"
                        else 0
                    )
                    if grain == "quarter":
                        offset //= 3
                    bucket_a = f"FLOOR((a.__period_index - {offset}) / {divisor}.0)"
                    bucket_b = f"FLOOR((b.__period_index - {offset}) / {divisor}.0)"
                    partition_a.append(bucket_a)
                    conditions.append(f"{bucket_a} = {bucket_b}")
                over = "PARTITION BY " + ", ".join(partition_a) + " " if partition_a else ""
                if self.needs_index:
                    over += "ORDER BY a.__period_index"
                same_series = " AND ".join(conditions) or "TRUE"
                for m in window.measure_ids:
                    name = f"{window.operation}_{m}"
                    if name in columns:
                        raise TypedCompileError(
                            "Multiple windows on the same measure need distinct approved output IDs"
                        )
                    if window.operation == "running_total":
                        expression = f"SUM(a.{m}) OVER ({over} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
                    elif window.operation == "moving_average":
                        if window.size is None:
                            raise RequestClarificationError(
                                "How many periods should the moving average cover?"
                            )
                        expression = f"(SELECT AVG(b.{m}) FROM {base} b WHERE {same_series} AND b.__period_index BETWEEN a.__period_index - {window.size - 1} AND a.__period_index)"
                        self.notes.append(
                            f"Moving averages use available observations within {window.size} calendar buckets; missing periods are not zero."
                        )
                    elif window.operation == "period_growth":
                        previous = f"(SELECT b.{m} FROM {base} b WHERE {same_series} AND b.__period_index = a.__period_index - 1)"
                        expression = f"100.0 * (a.{m} - {previous}) / NULLIF(ABS({previous}), 0)"
                        self.notes.append(
                            "Growth requires the immediately preceding calendar bucket; missing/zero baselines remain unavailable."
                        )
                    else:
                        denominator = (
                            "PARTITION BY " + ", ".join(partition_a) if partition_a else ""
                        )
                        expression = f"100.0 * a.{m} / NULLIF(SUM(a.{m}) OVER ({denominator}), 0)"
                    additions.append(f"{expression} AS {name}")
                    columns.append(name)
            base_columns = [m.id for m in req.measures if m.id not in self.unsupported]
            self.ctes.append(
                f"window_results AS (SELECT {', '.join([*('a.' + key for key in self.aliases.values()), *('a.' + key for key in base_columns), *additions])} FROM {base} a)"
            )
            base = "window_results"
        predicates = []
        for condition in req.measure_filters:
            if condition.measure_id not in columns:
                raise TypedCompileError(
                    "Measure filter is incompatible with this transformed result"
                )
            predicates.append(
                f"{condition.measure_id} "
                + {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[
                    condition.operator
                ]
                + " "
                + literal(condition.value)
            )
        selected = [*self.aliases.values(), *columns]
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        if req.ranking:
            metric = req.ranking.measure_id
            basis = req.ranking.basis
            if basis == "unspecified" and period_comparisons:
                basis = self.policy.comparison_ranking
                self.notes.append(
                    f"Comparison ranking uses the approved {basis.replace('_', ' ')} default."
                )
            if basis == "absolute_change":
                metric = f"change_{metric}"
            elif basis == "percent_change":
                metric = f"{metric}_change_pct"
            elif metric not in columns and period_comparisons:
                metric = f"current_{metric}"
            if metric not in columns:
                raise TypedCompileError("Ranking measure is unavailable in this result")
            order_sql = f"{metric} {req.ranking.direction.upper()} NULLS LAST"
            partition = [self.aliases[f] for f in req.ranking.partition_by if f in self.aliases]
            if len(partition) != len(req.ranking.partition_by):
                raise TypedCompileError("Ranking partitions must be grouped dimensions")
            rank_partition = "PARTITION BY " + ", ".join(partition) + " " if partition else ""
            if req.ranking.include_both_ends:
                self.ctes.append(
                    f"ranked AS (SELECT {', '.join(selected)}, DENSE_RANK() OVER ({rank_partition}ORDER BY {metric} DESC NULLS LAST) AS __top, DENSE_RANK() OVER ({rank_partition}ORDER BY {metric} ASC NULLS LAST) AS __bottom FROM {base}{where})"
                )
                base, where = "ranked", " WHERE __top = 1 OR __bottom = 1"
            elif req.ranking.ties == "include" or partition:
                function = "RANK" if req.ranking.ties == "include" else "ROW_NUMBER"
                self.ctes.append(
                    f"ranked AS (SELECT {', '.join(selected)}, {function}() OVER ({rank_partition}ORDER BY {order_sql}) AS __rank FROM {base}{where})"
                )
                base, where = "ranked", f" WHERE __rank <= {req.ranking.limit}"
            else:
                limit = min(limit, req.ranking.limit)
        else:
            order_sql = ", ".join(self.aliases.values()) if self.aliases else columns[0]
        coverage_columns = {}
        coverage_sql = []
        for period_name, source, cte in self.coverage_sources:
            for boundary, function in (("start", "MIN"), ("through", "MAX")):
                alias = f"__{period_name}_{source}_{boundary}"
                coverage_columns[alias] = (period_name, source, boundary)
                coverage_sql.append(
                    f"(SELECT {function}(__coverage_{boundary}) FROM {cte}) AS {alias}"
                )
        headlines = []
        if period_comparisons and not req.measure_filters and not req.operations:
            for measure in req.measures:
                if (
                    self.pack.model.measures[measure.id].aggregation == "sum"
                    and measure.id not in self.unsupported
                ):
                    for side in ("current", "baseline"):
                        headlines.append(
                            f"(SELECT SUM({side}_{measure.id}) FROM results) AS __headline_{side}_{measure.id}"
                        )
                    headlines.append(
                        f"(SELECT COUNT(*) FROM results WHERE current_{measure.id} IS NULL OR baseline_{measure.id} IS NULL) AS __missing_{measure.id}"
                    )
        outputs = [*selected, "COUNT(*) OVER () AS __total_groups", *coverage_sql, *headlines]
        sql = f"WITH {', '.join(self.ctes)} SELECT {', '.join(outputs)} FROM {base}{where} ORDER BY {order_sql} LIMIT {int(limit)}"
        # Parsing plus the same read-only guard used by Chat, independently of intent validation.
        sqlglot.parse_one(sql, read="postgres")
        safe, reason = sql_is_safe(sql)
        if not safe:
            raise TypedCompileError(reason or "Compiled query failed SQL safety validation")
        if self.unsupported:
            self.notes += [
                f"{key} unavailable: {reason}" for key, reason in self.unsupported.items()
            ]
        compiled = CompiledRequest(
            sql,
            req,
            selected,
            self.aliases,
            list(dict.fromkeys(self.notes)),
            self.unsupported,
            self.periods,
        )
        compiled.coverage_columns = coverage_columns
        return compiled


def compile_request(
    request: InterpretedRequest,
    *,
    pack: SemanticPackResponse,
    context: RequestContext,
    principal: RequestPrincipal,
    today: date,
    row_limit: int = 20,
) -> CompiledRequest:
    if request.analysis_tasks:
        raise TypedCompileError("A dependent inventory must use the reviewed analytical-plan compiler; it cannot be simplified to one ordinary request")
    if context.binding != principal.binding:
        raise TypedCompileError("Execution context belongs to another access scope")
    if context.semantic_version != pack_fingerprint(pack):
        raise TypedCompileError("Semantic metadata changed after interpretation; ask again")
    validate_proposal(request, context)
    return _Builder(pack, request, context, principal, today).build(min(200, max(1, row_limit)))
