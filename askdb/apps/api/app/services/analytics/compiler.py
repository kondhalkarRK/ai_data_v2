"""Governed SQL for Analytics Builder analyses.

Builds on the semantic compiler's metric, dimension, join and filter rules, and adds
what a BI builder needs: date ranges anchored to the latest loaded date, ranking
functions, moving windows, calendar-exact period growth, share of total, growth
contribution and actual vs target. Specs are checked by the catalog first; anything
reaching this module is a supported combination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import Industry
from app.schemas.analytics import AnalyticsSpec
from app.services.analytics.catalog import TARGET_METRICS, Catalog, Selection, parse_iso
from app.services.chat.question_understanding import ExtractedFilter, QuestionPlan, filter_predicate
from app.services.chat.semantic_analytics import (
    _ALIASES,
    _DATE_COLUMNS,
    DimensionSpec,
    MetricSpec,
    _dimension_expression,
    _dimension_specs,
    _join_clauses,
    _metric_spec,
    _model_tables,
    _validate_specs,
    _where_clauses,
)
from app.services.chat.time_periods import FISCAL_YEAR_START_MONTH, anchor_sql

MAX_ROWS = 500
_GRAIN_MONTHS = {"month": 1, "quarter": 3, "year": 12}
_GROWTH_NAME = {"month": "mom_growth_pct", "quarter": "qoq_growth_pct", "year": "yoy_growth_pct"}


class BuilderCompileError(ValueError):
    """The selection passed validation but could not be compiled (pack mismatch)."""


@dataclass(slots=True)
class DateWindow:
    """Half-open SQL date bounds; either side may be open."""

    start: str | None
    end: str | None
    label: str


@dataclass(slots=True)
class BuilderQuery:
    sql: str
    title: str
    analysis: str
    metric_column: str
    metric_format: str
    time_column: str | None = None
    time_grain: str | None = None
    category_columns: list[str] = field(default_factory=list)
    value_column: str = ""
    overlay_columns: list[str] = field(default_factory=list)
    date_label: str | None = None
    fact_table: str = ""
    date_column: str = ""
    notes: list[str] = field(default_factory=list)


def date_window(
    preset: str | None, date_from: str | None, date_to: str | None, anchor: str
) -> DateWindow | None:
    """SQL bounds for a preset, counted back from the latest loaded date (``anchor``)."""
    if not preset:
        return None
    day_after = f"({anchor} + INTERVAL '1 day')"
    month = f"date_trunc('month', {anchor})"
    quarter = f"date_trunc('quarter', {anchor})"
    year = f"date_trunc('year', {anchor})"
    shift = FISCAL_YEAR_START_MONTH - 1
    windows: dict[str, tuple[str | None, str | None, str]] = {
        "last_7_days": (f"({anchor} - INTERVAL '6 days')", day_after, "Last 7 days"),
        "last_30_days": (f"({anchor} - INTERVAL '29 days')", day_after, "Last 30 days"),
        "last_3_months": (f"({month} - INTERVAL '2 months')", day_after, "Last 3 months"),
        "last_6_months": (f"({month} - INTERVAL '5 months')", day_after, "Last 6 months"),
        "last_12_months": (f"({month} - INTERVAL '11 months')", day_after, "Last 12 months"),
        "last_24_months": (f"({month} - INTERVAL '23 months')", day_after, "Last 24 months"),
        "this_month": (month, day_after, "This month"),
        "last_month": (f"({month} - INTERVAL '1 month')", month, "Last month"),
        "this_quarter": (quarter, day_after, "This quarter"),
        "last_quarter": (f"({quarter} - INTERVAL '3 months')", quarter, "Last quarter"),
        "ytd": (year, day_after, "Year to date"),
        "fytd": (
            f"(date_trunc('year', {anchor} - INTERVAL '{shift} months') + INTERVAL '{shift} months')",
            day_after,
            "Fiscal year to date",
        ),
        "last_year": (f"({year} - INTERVAL '1 year')", year, "Last year"),
    }
    if preset == "custom":
        start, end = parse_iso(date_from), parse_iso(date_to)
        if start is None or end is None:
            return None
        return DateWindow(
            f"DATE '{start.isoformat()}'",
            f"(DATE '{end.isoformat()}' + INTERVAL '1 day')",
            f"{start.isoformat()} to {end.isoformat()}",
        )
    found = windows.get(preset)
    if found is None:
        return None
    return DateWindow(*found)


def compile_builder_query(spec: AnalyticsSpec, catalog: Catalog) -> BuilderQuery:
    selection = catalog.resolve(spec)
    if selection.metric is None or not selection.metric.supported:
        raise BuilderCompileError("No supported metric selected")
    return _Compiler(spec, selection, catalog).compile()


class _Compiler:
    def __init__(self, spec: AnalyticsSpec, selection: Selection, catalog: Catalog) -> None:
        self.spec = spec
        self.sel = selection
        self.catalog = catalog
        self.pack = catalog.pack
        self.industry = catalog.industry
        assert selection.metric is not None
        self.metric_def = selection.metric
        self.plan = QuestionPlan(
            industry=self.industry,
            intent="aggregation",
            entity="metric_only",
            metric=selection.metric.plan_metric,  # type: ignore[arg-type]
            filters=self._filters(),
            dimensions=[d.id for d in selection.dimensions],
            limit=spec.limit,
        )
        self.metric: MetricSpec = _metric_spec(self.plan)
        self.base_table = self.metric.table
        self.alias = _ALIASES[self.base_table]
        self.physical = str(
            getattr(_model_tables(self.pack)[self.base_table], "physical_name", self.base_table)
        )
        self.date_column = _DATE_COLUMNS[self.base_table]
        self.anchor = anchor_sql(self.physical, self.date_column)
        self.window = date_window(selection.date_preset, spec.date_from, spec.date_to, self.anchor)
        try:
            self.dims: list[DimensionSpec] = _dimension_specs(self.plan, self.base_table)
            _validate_specs(self.pack, self.metric, self.dims)
        except ValueError as exc:
            raise BuilderCompileError(str(exc)) from exc
        self.time_dim = next((d for d in self.dims if d.time_grain), None)
        self.cat_dims = [d for d in self.dims if not d.time_grain]

    # -- plan pieces --

    def _filters(self) -> list[ExtractedFilter]:
        filters: list[ExtractedFilter] = []
        for domain, raw, values in self.sel.filters:
            if domain is None:
                continue
            multi = len(values) > 1
            filters.append(
                ExtractedFilter(
                    column=domain.qualified_column,
                    operator="IN" if multi else "=",
                    value=values[0],
                    label=f"{raw} = {', '.join(values)}",
                    source="analytics_builder",
                    values=tuple(values) if multi else (),
                )
            )
        return filters

    def _where(self, *, lookback_months: int = 0) -> tuple[list[str], list[str]]:
        required: set[str] = {d.table for d in self.dims if d.table != self.base_table}
        try:
            where = _where_clauses(
                self.plan, self.pack, required, self.base_table, include_time=False
            )
            joins = _join_clauses(self.pack, self.base_table, required)
        except ValueError as exc:
            raise BuilderCompileError(str(exc)) from exc
        column = f"{self.alias}.{self.date_column}"
        if self.window is not None:
            if self.window.start:
                start = self.window.start
                if lookback_months:
                    start = f"({start} - INTERVAL '{lookback_months} months')"
                where.append(f"{column} >= {start}")
            if self.window.end:
                where.append(f"{column} < {self.window.end}")
        return where, joins

    def _aggregate(
        self, *, lookback_months: int = 0, extra_metrics: bool = False
    ) -> tuple[str, list[str]]:
        where, joins = self._where(lookback_months=lookback_months)
        expressions = [_dimension_expression(d) for d in self.dims]
        select = [f"{expr} AS {d.alias}" for expr, d in zip(expressions, self.dims, strict=True)]
        select.append(f"{self.metric.expression.format(alias=self.alias)} AS {self.metric.alias}")
        if extra_metrics:
            for extra in self.sel.extra_metrics:
                if extra.fact != self.metric_def.fact:
                    continue
                spec = _metric_spec(
                    QuestionPlan(
                        industry=self.industry,
                        intent="aggregation",
                        entity="metric_only",
                        metric=extra.plan_metric,
                    )
                )  # type: ignore[arg-type]
                if spec.alias not in {self.metric.alias}:
                    select.append(f"{spec.expression.format(alias=self.alias)} AS {spec.alias}")
        sql = (
            "SELECT "
            + ",\n       ".join(select)
            + f"\nFROM {self.physical} {self.alias}"
            + ("\n" + "\n".join(joins) if joins else "")
            + (f"\nWHERE {' AND '.join(where)}" if where else "")
            + (f"\nGROUP BY {', '.join(expressions)}" if expressions else "")
        )
        return sql, [d.alias for d in self.dims]

    def _period_floor(self, prefix: str = "") -> str | None:
        """Keep only periods inside the selected range after a lookback."""
        if self.window is None or not self.window.start or self.time_dim is None:
            return None
        grain = self.time_dim.time_grain or "month"
        column = f"{prefix}{self.time_dim.alias}"
        if grain == "year":
            return f"{column} >= EXTRACT(YEAR FROM {self.window.start})::int"
        return f"{column} >= date_trunc('{grain}', {self.window.start})::date"

    def _share_partition(self) -> list[str]:
        """Share within each period when time is present, else within the first group."""
        if len(self.dims) < 2:
            return []
        if self.time_dim is not None:
            return [self.time_dim.alias]
        return [self.dims[0].alias]

    # -- dispatch --

    def compile(self) -> BuilderQuery:
        analysis = self.sel.analysis.id
        handler = getattr(self, f"_render_{analysis}", None)
        if handler is None:
            raise BuilderCompileError(f"Analysis '{analysis}' is not available")
        query: BuilderQuery = handler()
        query.analysis = analysis
        query.metric_format = self.metric_def.format
        query.date_label = self.window.label if self.window else None
        query.fact_table = self.physical
        query.date_column = self.date_column
        if not query.value_column:
            query.value_column = query.metric_column
        return query

    def _query(self, sql: str, title: str, **extra: Any) -> BuilderQuery:
        return BuilderQuery(
            sql=sql.strip(),
            title=title,
            analysis="",
            metric_column=self.metric.alias,
            metric_format="",
            time_column=self.time_dim.alias if self.time_dim else None,
            time_grain=self.time_dim.time_grain if self.time_dim else None,
            category_columns=[d.alias for d in self.cat_dims],
            **extra,
        )

    def _title(self, prefix: str = "", suffix: str = "") -> str:
        metric = self.catalog.metric_label(self.metric_def)
        by = [d.label for d in self.sel.dimensions]
        core = f"{metric} by {' and '.join(by)}" if by else metric
        return " ".join(part for part in (prefix, core, suffix) if part).strip()

    # -- standard shapes --

    def _ordered(self, aggregate: str) -> str:
        if self.time_dim is not None:
            order = ", ".join([self.time_dim.alias, *(d.alias for d in self.cat_dims)])
            return f"{aggregate}\nORDER BY {order}\nLIMIT {MAX_ROWS}"
        if self.cat_dims:
            return f"{aggregate}\nORDER BY {self.metric.alias} DESC NULLS LAST\nLIMIT {self.spec.limit}"
        return aggregate

    def _render_basic(self) -> BuilderQuery:
        aggregate, _ = self._aggregate(extra_metrics=True)
        return self._query(self._ordered(aggregate), self._title())

    def _render_trend(self) -> BuilderQuery:
        aggregate, _ = self._aggregate(extra_metrics=True)
        return self._query(self._ordered(aggregate), self._title(suffix="trend"))

    def _render_comparison(self) -> BuilderQuery:
        aggregate, _ = self._aggregate(extra_metrics=True)
        values = next((v for dom, _r, v in self.sel.filters if dom is not None), [])
        title = f"{self.catalog.metric_label(self.metric_def)}: {' vs '.join(values[:4])}"
        if self.time_dim is not None:
            title += f" by {self.time_dim.alias}"
        return self._query(self._ordered(aggregate), title)

    # -- ranking --

    def _ranked(
        self, *, function: str, direction: str, partition: list[str], keep: int | None
    ) -> str:
        aggregate, _ = self._aggregate()
        over = (f"PARTITION BY {', '.join(partition)} " if partition else "") + (
            f"ORDER BY {self.metric.alias} {direction} NULLS LAST"
        )
        rank_name = {"ROW_NUMBER": "row_number", "DENSE_RANK": "dense_rank"}.get(function, "rank")
        keep_sql = f"\nWHERE {rank_name} <= {int(keep)}" if keep else ""
        order = ", ".join([*partition, rank_name])
        return f"""WITH base AS (
  {_indent(aggregate)}
), ranked AS (
  SELECT base.*, {function}() OVER ({over}) AS {rank_name}
  FROM base
)
SELECT *
FROM ranked{keep_sql}
ORDER BY {order}
LIMIT {MAX_ROWS}"""

    def _render_top_n(self) -> BuilderQuery:
        sql = self._ranked(
            function="ROW_NUMBER", direction="DESC", partition=[], keep=self.spec.limit
        )
        return self._query(sql, self._title(prefix=f"Top {self.spec.limit}"))

    def _render_bottom_n(self) -> BuilderQuery:
        sql = self._ranked(
            function="ROW_NUMBER", direction="ASC", partition=[], keep=self.spec.limit
        )
        return self._query(sql, self._title(prefix=f"Bottom {self.spec.limit}"))

    def _render_top_n_per_group(self) -> BuilderQuery:
        group, item = self.dims[0], self.dims[1]
        sql = self._ranked(
            function="ROW_NUMBER", direction="DESC", partition=[group.alias], keep=self.spec.limit
        )
        labels = [d.label for d in self.sel.dimensions]
        title = (
            f"Top {self.spec.limit} {labels[1].lower()}s within each {labels[0].lower()} "
            f"by {self.catalog.metric_label(self.metric_def).lower()}"
        )
        query = self._query(sql, title)
        query.category_columns = [group.alias, item.alias] if not group.time_grain else [item.alias]
        return query

    def _render_ranking(self) -> BuilderQuery:
        function = {"dense_rank": "DENSE_RANK", "row_number": "ROW_NUMBER"}.get(
            self.spec.rank_method, "RANK"
        )
        ranked = self.cat_dims[-1]
        partition = [d.alias for d in self.dims if d is not ranked]
        sql = self._ranked(
            function=function, direction="DESC", partition=partition, keep=self.spec.limit
        )
        method = {"RANK": "Rank", "DENSE_RANK": "Dense rank", "ROW_NUMBER": "Row number"}[function]
        query = self._query(sql, self._title(prefix=f"{method}:"))
        if partition:
            query.notes.append(f"Ranked within each {self.sel.dimensions[0].label.lower()}.")
        return query

    # -- distribution --

    def _render_contribution(self) -> BuilderQuery:
        aggregate, _ = self._aggregate()
        partition = self._share_partition()
        over = f"PARTITION BY {', '.join(partition)}" if partition else ""
        m = self.metric.alias
        share = f"{m}_share_pct"
        cumulative = ""
        if not partition:
            cumulative = (
                f",\n         100.0 * SUM({m}) OVER (ORDER BY {m} DESC NULLS LAST ROWS BETWEEN UNBOUNDED "
                f"PRECEDING AND CURRENT ROW) / NULLIF(SUM({m}) OVER (), 0) AS cumulative_share_pct"
            )
        order = ", ".join([*partition, f"{m} DESC NULLS LAST"])
        limit = MAX_ROWS if partition else self.spec.limit
        sql = f"""WITH base AS (
  {_indent(aggregate)}
)
SELECT base.*,
         100.0 * {m} / NULLIF(SUM({m}) OVER ({over}), 0) AS {share}{cumulative}
FROM base
ORDER BY {order}
LIMIT {limit}"""
        query = self._query(sql, self._title(prefix="Share of"))
        query.value_column = share
        return query

    # -- time intelligence --

    def _render_running_total(self) -> BuilderQuery:
        assert self.time_dim is not None
        aggregate, _ = self._aggregate()
        partition = [d.alias for d in self.cat_dims]
        over = (
            f"PARTITION BY {', '.join(partition)} " if partition else ""
        ) + f"ORDER BY {self.time_dim.alias}"
        running = f"running_{self.metric.alias}"
        order = ", ".join([*partition, self.time_dim.alias])
        sql = f"""WITH base AS (
  {_indent(aggregate)}
)
SELECT base.*,
       SUM({self.metric.alias}) OVER ({over} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS {running}
FROM base
ORDER BY {order}
LIMIT {MAX_ROWS}"""
        query = self._query(sql, self._title(prefix="Running total of"))
        query.value_column = running
        return query

    def _render_moving_average(self) -> BuilderQuery:
        assert self.time_dim is not None
        periods = max(2, min(self.spec.window, 24))
        grain = self.time_dim.time_grain or "month"
        lookback = (periods - 1) * _GRAIN_MONTHS[grain]
        aggregate, _ = self._aggregate(lookback_months=lookback)
        partition = [d.alias for d in self.cat_dims]
        over = (f"PARTITION BY {', '.join(partition)} " if partition else "") + (
            f"ORDER BY {self.time_dim.alias} ROWS BETWEEN {periods - 1} PRECEDING AND CURRENT ROW"
        )
        moving = f"moving_avg_{self.metric.alias}"
        floor = self._period_floor()
        order = ", ".join([*partition, self.time_dim.alias])
        sql = f"""WITH base AS (
  {_indent(aggregate)}
), smoothed AS (
  SELECT base.*,
         CASE WHEN COUNT(*) OVER ({over}) >= {periods}
              THEN AVG({self.metric.alias}) OVER ({over}) END AS {moving}
  FROM base
)
SELECT *
FROM smoothed{f"{chr(10)}WHERE {floor}" if floor else ""}
ORDER BY {order}
LIMIT {MAX_ROWS}"""
        query = self._query(sql, self._title(prefix=f"{periods}-{grain} moving average of"))
        query.value_column = moving
        query.overlay_columns = [self.metric.alias, moving]
        query.notes.append(
            f"Each point averages the latest {periods} {grain}s; the first points stay blank until "
            f"{periods} {grain}s of history are available."
        )
        return query

    def _growth(self, *, shift_months: int, name: str, label: str) -> BuilderQuery:
        assert self.time_dim is not None
        aggregate, _ = self._aggregate(lookback_months=shift_months)
        t = self.time_dim.alias
        m = self.metric.alias
        if self.time_dim.time_grain == "year":
            previous_period = f"cur.{t} - {max(1, shift_months // 12)}"
        else:
            previous_period = f"(cur.{t} - INTERVAL '{shift_months} months')::date"
        joins = [f"prev.{t} = {previous_period}"] + [
            f"prev.{d.alias} IS NOT DISTINCT FROM cur.{d.alias}" for d in self.cat_dims
        ]
        floor = self._period_floor("cur.")
        partition = [d.alias for d in self.cat_dims]
        order = ", ".join([*(f"cur.{p}" for p in partition), f"cur.{t}"])
        sql = f"""WITH base AS (
  {_indent(aggregate)}
)
SELECT cur.*,
       prev.{m} AS previous_{m},
       100.0 * (cur.{m} - prev.{m}) / NULLIF(prev.{m}, 0) AS {name}
FROM base cur
LEFT JOIN base prev ON {" AND ".join(joins)}{f"{chr(10)}WHERE {floor}" if floor else ""}
ORDER BY {order}
LIMIT {MAX_ROWS}"""
        query = self._query(sql, self._title(prefix=label))
        query.value_column = name
        return query

    def _render_period_growth(self) -> BuilderQuery:
        assert self.time_dim is not None
        grain = self.time_dim.time_grain or "month"
        label = {"month": "MoM growth in", "quarter": "QoQ growth in", "year": "YoY growth in"}[
            grain
        ]
        return self._growth(
            shift_months=_GRAIN_MONTHS[grain], name=_GROWTH_NAME[grain], label=label
        )

    def _render_yoy_growth(self) -> BuilderQuery:
        return self._growth(shift_months=12, name="yoy_growth_pct", label="YoY growth in")

    def _render_growth_contribution(self) -> BuilderQuery:
        dim = self.cat_dims[0]
        column = f"{self.alias}.{self.date_column}"
        if self.window is not None and self.window.start and self.window.end:
            current_start, current_end = self.window.start, self.window.end
            period_label = f"{self.window.label} vs the equivalent prior period"
        else:
            current_start = f"(date_trunc('month', {self.anchor}) - INTERVAL '11 months')"
            current_end = f"({self.anchor} + INTERVAL '1 day')"
            period_label = "latest 12 months vs the prior 12 months"
        span = f"(({current_end})::date - ({current_start})::date)"
        previous_start = f"(({current_start})::date - {span})"
        saved_window, self.window = self.window, None
        where, joins = self._where()
        self.window = saved_window
        expr = _dimension_expression(dim)
        m_expr = self.metric.expression.format(alias=self.alias)
        bucket = f"CASE WHEN {column} >= {current_start} THEN 'current' ELSE 'previous' END"
        where = [*where, f"{column} >= {previous_start}", f"{column} < {current_end}"]
        m = self.metric.alias
        sql = f"""WITH bucketed AS (
  SELECT {expr} AS {dim.alias},
         {bucket} AS period_bucket,
         {m_expr} AS {m}
  FROM {self.physical} {self.alias}
  {chr(10).join("  " + j for j in joins).strip()}
  WHERE {" AND ".join(where)}
  GROUP BY {expr}, {bucket}
), compared AS (
  SELECT {dim.alias},
         COALESCE(MAX({m}) FILTER (WHERE period_bucket = 'current'), 0) AS current_{m},
         COALESCE(MAX({m}) FILTER (WHERE period_bucket = 'previous'), 0) AS previous_{m}
  FROM bucketed
  GROUP BY {dim.alias}
)
SELECT compared.*,
       current_{m} - previous_{m} AS change_{m},
       100.0 * (current_{m} - previous_{m}) / NULLIF(previous_{m}, 0) AS change_pct,
       100.0 * (current_{m} - previous_{m}) / NULLIF(SUM(current_{m} - previous_{m}) OVER (), 0)
         AS contribution_to_change_pct
FROM compared
ORDER BY change_{m} DESC
LIMIT {self.spec.limit}"""
        query = self._query(
            sql, self._title(prefix="Growth contribution:", suffix=f"({period_label})")
        )
        query.value_column = f"change_{m}"
        query.overlay_columns = [f"current_{m}", f"previous_{m}"]
        query.notes.append(f"Compares the {period_label}.")
        query.date_label = period_label
        return query

    def _render_above_average(self) -> BuilderQuery:
        aggregate, _ = self._aggregate()
        partition = self._share_partition()
        over = f"PARTITION BY {', '.join(partition)}" if partition else ""
        m = self.metric.alias
        sql = f"""WITH base AS (
  {_indent(aggregate)}
), compared AS (
  SELECT base.*,
         AVG({m}) OVER ({over}) AS average_{m}
  FROM base
)
SELECT compared.*,
       100.0 * ({m} - average_{m}) / NULLIF(average_{m}, 0) AS above_average_pct
FROM compared
WHERE {m} > average_{m}
ORDER BY {", ".join([*partition, f"{m} DESC"])}
LIMIT {MAX_ROWS if partition else self.spec.limit}"""
        query = self._query(sql, self._title(prefix="Above-average"))
        query.overlay_columns = [m, f"average_{m}"]
        return query

    # -- variance --

    def _render_actual_vs_target(self) -> BuilderQuery:
        if self.industry is not Industry.AUTOMOTIVE:
            raise BuilderCompileError("Targets are only available for automotive data")
        target_column = TARGET_METRICS[self.metric_def.id]
        tables = _model_tables(self.pack)
        target_physical = str(
            getattr(tables.get("dim_targets"), "physical_name", "automotive.dim_targets")
        )
        carline_physical = str(
            getattr(tables.get("dim_carline"), "physical_name", "automotive.dim_carline")
        )
        complete = f"date_trunc('month', {self.anchor} + INTERVAL '1 day')"

        actual_cols: list[str] = []
        target_cols: list[str] = []
        names: list[str] = []
        for dim in self.sel.dimensions:
            if dim.id == "make":
                actual_cols.append("v.make AS make")
                target_cols.append("t.make AS make")
                names.append("make")
            else:
                grain = dim.id
                if grain == "year":
                    actual_cols.append("EXTRACT(YEAR FROM f.sales_date)::int AS year")
                    target_cols.append("EXTRACT(YEAR FROM t.year_month)::int AS year")
                else:
                    actual_cols.append(f"date_trunc('{grain}', f.sales_date)::date AS {grain}")
                    target_cols.append(f"date_trunc('{grain}', t.year_month)::date AS {grain}")
                names.append(grain)

        actual_where = [f"f.sales_date < {complete}"]
        target_where = [f"t.year_month < {complete}"]
        if self.window is not None:
            if self.window.start:
                actual_where.append(f"f.sales_date >= {self.window.start}")
                target_where.append(f"t.year_month >= date_trunc('month', {self.window.start})")
            if self.window.end:
                actual_where.append(f"f.sales_date < {self.window.end}")
                target_where.append(f"t.year_month < {self.window.end}")
        for filt in self.plan.filters:
            actual_where.append(filter_predicate("v.make", filt))
            target_where.append(filter_predicate("t.make", filt))

        group_a = ", ".join(str(i + 1) for i in range(len(names)))
        actual_metric = (
            "SUM(f.total_sales)" if self.metric_def.id == "revenue" else "SUM(f.order_qty)"
        )
        time_name = next((n for n in names if n != "make"), None)
        order = (
            ", ".join(n for n in (time_name, "make") if n in names)
            if time_name
            else "achievement_pct DESC NULLS LAST"
        )
        sql = f"""WITH actual AS (
  SELECT {", ".join(actual_cols)}, {actual_metric} AS actual
  FROM {self.physical} f
  JOIN {carline_physical} v ON v.carline_id = f.carline_id
  WHERE {" AND ".join(actual_where)}
  GROUP BY {group_a}
), target AS (
  SELECT {", ".join(target_cols)}, SUM(t.{target_column}) AS target
  FROM {target_physical} t
  WHERE {" AND ".join(target_where)}
  GROUP BY {group_a}
)
SELECT {", ".join(names)},
       COALESCE(actual.actual, 0) AS actual,
       target.target AS target,
       COALESCE(actual.actual, 0) - target.target AS variance,
       100.0 * COALESCE(actual.actual, 0) / NULLIF(target.target, 0) AS achievement_pct
FROM actual
FULL OUTER JOIN target USING ({", ".join(names)})
ORDER BY {order}
LIMIT {MAX_ROWS}"""
        metric_label = self.catalog.metric_label(self.metric_def)
        query = self._query(
            sql,
            f"{metric_label}: actual vs target by {' and '.join(d.label for d in self.sel.dimensions)}",
        )
        query.metric_column = "actual"
        query.value_column = "achievement_pct"
        query.overlay_columns = ["actual", "target"]
        query.time_column = time_name
        query.time_grain = time_name
        query.category_columns = ["make"] if "make" in names else []
        query.notes.append(
            "Complete months only, so a month in progress isn't compared with a full-month target."
        )
        return query


def driver_sql(
    spec: AnalyticsSpec, catalog: Catalog, *, grain: str, dimension: str
) -> tuple[str, str] | None:
    """Latest complete period vs the one before, per ``dimension``: who moved the total."""
    probe = spec.model_copy(update={"dimensions": [dimension], "analysis": "basic"})
    selection = catalog.resolve(probe)
    if selection.metric is None or not selection.metric.supported or not selection.metric.additive:
        return None
    try:
        compiler = _Compiler(probe, selection, catalog)
    except BuilderCompileError:
        return None
    column = f"{compiler.alias}.{compiler.date_column}"
    end = f"({compiler.anchor} + INTERVAL '1 day')"
    if compiler.window is not None and compiler.window.end:
        end = f"LEAST({compiler.window.end}, {end})"
    current_start = f"(date_trunc('{grain}', {end}) - INTERVAL '1 {grain}')"
    current_end = f"date_trunc('{grain}', {end})"
    previous_start = f"({current_start} - INTERVAL '1 {grain}')"
    saved, compiler.window = compiler.window, None
    where, joins = compiler._where()
    compiler.window = saved
    dim = compiler.dims[0]
    expr = _dimension_expression(dim)
    m_expr = compiler.metric.expression.format(alias=compiler.alias)
    bucket = f"CASE WHEN {column} >= {current_start} THEN 'current' ELSE 'previous' END"
    where = [*where, f"{column} >= {previous_start}", f"{column} < {current_end}"]
    sql = f"""WITH bucketed AS (
  SELECT {expr} AS label, {bucket} AS period_bucket, {m_expr} AS value
  FROM {compiler.physical} {compiler.alias}
  {chr(10).join("  " + j for j in joins).strip()}
  WHERE {" AND ".join(where)}
  GROUP BY {expr}, {bucket}
)
SELECT label,
       COALESCE(MAX(value) FILTER (WHERE period_bucket = 'current'), 0) AS current_value,
       COALESCE(MAX(value) FILTER (WHERE period_bucket = 'previous'), 0) AS previous_value,
       ({current_start})::date AS period_start
FROM bucketed
GROUP BY label
ORDER BY current_value DESC
LIMIT 200"""
    return sql, dim.alias


def _indent(sql: str) -> str:
    return sql.replace("\n", "\n  ")
