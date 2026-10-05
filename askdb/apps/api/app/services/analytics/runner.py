"""Execute Analytics Builder specs.

Every run is checked against the capability catalog first, so an unsupported
combination returns a business explanation with one-click fixes instead of a SQL
error. Valid specs compile to governed SQL (``compiler.py``) and run read-only with a
timeout; warehouse failures are reported in plain language and logged in full.
"""

from __future__ import annotations

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry, Settings
from app.core.exceptions import NotFoundError, NqlError
from app.db.session import DatabaseRegistry
from app.models.activity import SavedAnalysis
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsAssistRequest,
    AnalyticsAssistResponse,
    AnalyticsCapabilities,
    AnalyticsChartPayload,
    AnalyticsFilterSpec,
    AnalyticsInsights,
    AnalyticsInspection,
    AnalyticsRunResponse,
    AnalyticsSpec,
    AnalyticsVizKind,
    FilterValueItem,
    FilterValuesResponse,
    SavedAnalysisCreate,
    SavedAnalysisResponse,
    SavedAnalysisUpdate,
)
from app.semantic.service import SemanticService
from app.services.analytics.catalog import Catalog, first_error
from app.services.analytics.compiler import (
    MAX_ROWS,
    BuilderCompileError,
    BuilderQuery,
    compile_builder_query,
    driver_sql,
)
from app.services.analytics.insights import (
    DriverResult,
    InsightContext,
    build_narration,
    period_name,
)
from app.services.analytics.spec_to_plan import AnalyticsSpecError
from app.services.chat.question_understanding import QuestionPlan, understand_question
from app.services.chat.response_meta import build_insights
from app.services.chat.semantic_analytics import SemanticCompileError
from app.services.chat.value_dictionary import BusinessValue, get_value_dictionary

logger = logging.getLogger(__name__)

_PRIMARY_FACT = {
    Industry.AUTOMOTIVE: ("automotive.fact_sales", "sales_date"),
    Industry.INSURANCE: ("insurance.fact_policy_monthly", "accounting_month"),
}
_DRIVER_DIMENSION = {
    Industry.AUTOMOTIVE: ("model", "Model"),
    Industry.INSURANCE: ("product", "Product"),
}
_DRIVER_ANALYSES = frozenset(
    {"basic", "trend", "period_growth", "yoy_growth", "moving_average", "running_total"}
)
_MAX_SERIES = 6


class AnalyticsRunError(NqlError):
    status_code = 422
    code = "analytics_run_failed"
    message = "The analysis could not be executed."


class AnalyticsValidationError(NqlError):
    status_code = 422
    code = "analytics_invalid_selection"
    message = "This combination can't be analysed yet."


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def catalog_for(semantic: SemanticService, industry: Industry) -> Catalog:
    return Catalog(industry, await semantic.get_pack(industry))


async def inspect_spec(
    semantic: SemanticService, industry: Industry, spec: AnalyticsSpec
) -> AnalyticsInspection:
    """Validation and guidance without touching the warehouse."""
    return (await catalog_for(semantic, industry)).inspect(spec)


async def capabilities_for(
    semantic: SemanticService, industry: Industry, registry: DatabaseRegistry
) -> AnalyticsCapabilities:
    """Builder options come from the semantic pack; the warehouse only supplies the
    "data through" date, so an unreachable warehouse must not hide the options."""
    catalog = await catalog_for(semantic, industry)
    as_of: date | None = None
    try:
        async with registry.analytics_connection(industry) as connection:
            as_of = await _latest_date(connection, *_PRIMARY_FACT[industry])
    except Exception:
        logger.warning("Analytics warehouse unavailable for capabilities", exc_info=True)
    return catalog.capabilities(data_as_of=as_of.isoformat() if as_of else None)


async def _latest_date(connection: AsyncConnection, table: str, column: str) -> date | None:
    if not table or not column:
        return None
    try:
        value = (await connection.execute(text(f"SELECT MAX({column}) FROM {table}"))).scalar()
    except Exception:
        logger.warning("Could not read the latest date of %s", table, exc_info=True)
        return None
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


class AnalyticsService:
    def __init__(
        self,
        *,
        app_session: AsyncSession,
        analytics: AsyncConnection,
        settings: Settings,
        user: User,
        industry: Industry,
        semantic_service: SemanticService,
    ) -> None:
        self._app = app_session
        self._analytics = analytics
        self._settings = settings
        self._user = user
        self._industry = industry
        self._semantic = semantic_service

    # -- capabilities --

    async def capabilities(self) -> AnalyticsCapabilities:
        catalog = await catalog_for(self._semantic, self._industry)
        as_of = await self._data_as_of(*_PRIMARY_FACT[self._industry])
        return catalog.capabilities(data_as_of=as_of.isoformat() if as_of else None)

    # -- run --

    async def run(self, spec: AnalyticsSpec) -> AnalyticsRunResponse:
        catalog = await catalog_for(self._semantic, self._industry)
        report = catalog.inspect(spec)
        blocking = first_error(report.issues)
        if blocking is not None:
            raise AnalyticsValidationError(
                blocking.message,
                details={
                    "issues": [issue.model_dump(by_alias=True) for issue in report.issues],
                    "suggestions": [s.model_dump(by_alias=True) for s in report.suggestions[:4]],
                },
            )
        try:
            query = compile_builder_query(spec, catalog)
        except (BuilderCompileError, SemanticCompileError, ValueError) as exc:
            logger.warning("Analytics Builder could not compile a validated spec: %s", exc)
            raise AnalyticsRunError(
                "This combination isn't supported by the data model yet. Try one of the suggestions.",
                details={
                    "suggestions": [s.model_dump(by_alias=True) for s in report.suggestions[:4]]
                },
            ) from exc

        await self._prepare()
        try:
            result = await self._analytics.execute(text(query.sql))
            mappings = result.mappings().fetchmany(MAX_ROWS + 1)
            columns = list(result.keys())
        except Exception as exc:
            logger.exception("Analytics Builder SQL failed")
            raise AnalyticsRunError(_friendly_failure(exc), code="analytics_query_failed") from exc

        truncated = len(mappings) > MAX_ROWS
        rows = [
            {key: _jsonable(value) for key, value in row.items()} for row in mappings[:MAX_ROWS]
        ]

        as_of = await self._data_as_of(query.fact_table, query.date_column)
        partial = _partial_period(query, as_of, rows)
        driver = await self._driver(spec, catalog, query) if rows else None

        metric_def = catalog.resolve(spec).metric
        metric_label = catalog.metric_label(metric_def) if metric_def else query.metric_column
        narration = build_narration(
            InsightContext(
                query=query,
                columns=columns,
                rows=rows,
                metric_label=metric_label,
                partial_period=partial,
                driver=driver,
            )
        )
        if narration is not None:
            insights = AnalyticsInsights(
                executive=narration.executive_text(),
                analyst=narration.analyst_text(),
                narration=narration.to_dict(),
            )
        else:
            payload = build_insights(
                narrative=query.title, columns=columns, rows=rows, path="analytics_builder"
            )
            insights = AnalyticsInsights(executive=payload["executive"], analyst=payload["analyst"])

        chart, viz = build_chart(query, columns, rows, spec.viz)
        warnings = [issue.message for issue in report.issues if issue.severity == "warning"]
        notes = list(query.notes)
        if truncated:
            notes.append(f"Showing the first {MAX_ROWS} rows; add a filter to narrow the result.")
        if not rows:
            notes.append("No data matches this selection. Widen the date range or remove a filter.")

        return AnalyticsRunResponse(
            title=query.title,
            columns=columns,
            rows=rows,
            sql=query.sql,
            chart=chart,
            recommended_viz=viz,
            insights=insights,
            meta={
                "path": "analytics_builder",
                "analysis": query.analysis,
                "metric": metric_def.id if metric_def else None,
                "metricFormat": query.metric_format,
                "valueColumn": query.value_column,
                "dimensions": [d.id for d in catalog.resolve(spec).dimensions],
                "rowCount": len(rows),
                "truncated": truncated,
                "dataAsOf": as_of.isoformat() if as_of else None,
                "dateLabel": query.date_label,
                "partialPeriod": partial,
                "notes": notes,
                "warnings": warnings,
            },
        )

    async def _prepare(self) -> None:
        try:
            await self._analytics.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:
            logger.debug("Read-only transaction already set", exc_info=True)
        timeout_ms = int(self._settings.nlq_sql_timeout_seconds * 1000)
        await self._analytics.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))

    async def _data_as_of(self, table: str, column: str) -> date | None:
        return await _latest_date(self._analytics, table, column)

    async def _driver(
        self, spec: AnalyticsSpec, catalog: Catalog, query: BuilderQuery
    ) -> DriverResult | None:
        if (
            query.analysis not in _DRIVER_ANALYSES
            or not query.time_column
            or query.category_columns
        ):
            return None
        dimension, label = _DRIVER_DIMENSION[self._industry]
        compiled = driver_sql(spec, catalog, grain=query.time_grain or "month", dimension=dimension)
        if compiled is None:
            return None
        sql, _ = compiled
        try:
            result = await self._analytics.execute(text(sql))
            records = result.mappings().all()
        except Exception:
            logger.warning("Analytics Builder driver query failed", exc_info=True)
            return None
        if not records:
            return None
        start = records[0].get("period_start")
        grain = query.time_grain or "month"
        if isinstance(start, datetime):
            start = start.date()
        current = period_name(start, grain) if isinstance(start, date) else f"the latest {grain}"
        previous = (
            period_name(_shift(start, grain, -1), grain)
            if isinstance(start, date)
            else f"the {grain} before"
        )
        return DriverResult(
            dimension_label=label,
            period_label=current,
            previous_label=previous,
            rows=[
                (str(r["label"]), float(r["current_value"] or 0), float(r["previous_value"] or 0))
                for r in records
                if r["label"] is not None
            ],
        )

    # -- assist --

    async def assist(self, body: AnalyticsAssistRequest) -> AnalyticsAssistResponse:
        catalog = await catalog_for(self._semantic, self._industry)
        dictionary = await get_value_dictionary(self._analytics, self._industry, pack=catalog.pack)
        plan = understand_question(
            self._industry, body.prompt, value_filters=dictionary.match(body.prompt)
        )
        spec = assist_spec(plan, catalog)
        report = catalog.inspect(spec)
        bits: list[str] = []
        metric = catalog.metric(spec.metrics[0]) if spec.metrics else None
        if metric is not None:
            bits.append(f"Metric: {catalog.metric_label(metric)}")
        dims = [d.label for raw in spec.dimensions if (d := catalog.dimension(raw))]
        if dims:
            bits.append(f"Split by: {', '.join(dims)}")
        if spec.filters:
            bits.append(
                "Filters: " + ", ".join(f"{f.domain} = {', '.join(f.values)}" for f in spec.filters)
            )
        if spec.analysis != "basic":
            label = next((a.label for a in report.analyses if a.id == spec.analysis), spec.analysis)
            bits.append(f"Analysis: {label}")
        if spec.date_preset:
            bits.append(f"Period: {spec.date_preset.replace('_', ' ')}")
        explanation = "Filled in from your prompt. " + (
            " \u00b7 ".join(bits) if bits else "Adjust the fields and run."
        )
        blocking = first_error(report.issues)
        if blocking is not None:
            explanation += f" Note: {blocking.message}"
        return AnalyticsAssistResponse(
            spec=spec, explanation=explanation, glossary_hits=list(plan.glossary_hits)
        )

    # -- filter values --

    async def filter_values(
        self,
        domain: str,
        *,
        q: str | None = None,
        parent_domain: str | None = None,
        parent_values: list[str] | None = None,
        limit: int = 80,
    ) -> FilterValuesResponse:
        pack = await self._semantic.get_pack(self._industry)
        dictionary = await get_value_dictionary(self._analytics, self._industry, pack=pack)
        catalog = Catalog(self._industry, pack)
        matched = catalog.domain(domain)
        if matched is None:
            raise AnalyticsSpecError(
                f"Unknown filter domain '{domain}'.", details={"domain": domain}
            )

        values = [
            v
            for v in dictionary.values
            if v.column == matched.qualified_column
            or v.domain.casefold() == matched.name.casefold()
        ]

        # Cascading: when parent filters are on the same table, re-query distinct values.
        if parent_domain and parent_values:
            parent = catalog.domain(parent_domain)
            if parent is not None and parent.table == matched.table:
                placeholders = ", ".join(f"'{_sql_literal(v)}'" for v in parent_values)
                sql = (
                    f"SELECT {matched.column}::text AS value, COUNT(*)::bigint AS frequency "
                    f"FROM {matched.table} "
                    f"WHERE {matched.column} IS NOT NULL AND {matched.column}::text <> '' "
                    f"AND {parent.column}::text IN ({placeholders}) "
                    f"GROUP BY {matched.column} "
                    f"ORDER BY frequency DESC, value "
                    f"LIMIT {int(limit)}"
                )
                try:
                    result = await self._analytics.execute(text(sql))
                    values = [
                        BusinessValue(
                            domain=matched.name,
                            column=matched.qualified_column,
                            value=str(row.value),
                            frequency=int(row.frequency or 0),
                        )
                        for row in result
                    ]
                except Exception:
                    logger.exception("Cascading filter query failed; using dictionary")

        needle_q = (q or "").strip().casefold()
        items: list[FilterValueItem] = []
        for item in values:
            if needle_q and needle_q not in item.value.casefold():
                continue
            items.append(
                FilterValueItem(value=item.value, frequency=item.frequency, label=item.value)
            )
            if len(items) >= limit:
                break
        return FilterValuesResponse(domain=matched.name, label=matched.label, values=items)

    # -- saved analyses --

    async def list_analyses(self) -> list[SavedAnalysisResponse]:
        rows = (
            (
                await self._app.execute(
                    select(SavedAnalysis)
                    .where(SavedAnalysis.user_id == self._user.id)
                    .where(SavedAnalysis.industry == self._industry.value)
                    .order_by(SavedAnalysis.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [_to_saved(row) for row in rows]

    async def create_analysis(self, body: SavedAnalysisCreate) -> SavedAnalysisResponse:
        row = SavedAnalysis(
            user_id=self._user.id,
            industry=self._industry.value,
            title=body.title.strip(),
            spec=body.spec.model_dump(by_alias=True),
            viz=body.viz,
            sql_snapshot=body.sql_snapshot,
        )
        self._app.add(row)
        await self._app.flush()
        return _to_saved(row)

    async def update_analysis(
        self, analysis_id: UUID, body: SavedAnalysisUpdate
    ) -> SavedAnalysisResponse:
        row = await self._get_owned(analysis_id)
        if body.title is not None:
            row.title = body.title.strip()
        if body.spec is not None:
            row.spec = body.spec.model_dump(by_alias=True)
        if body.viz is not None:
            row.viz = body.viz
        if body.sql_snapshot is not None:
            row.sql_snapshot = body.sql_snapshot
        await self._app.flush()
        return _to_saved(row)

    async def delete_analysis(self, analysis_id: UUID) -> None:
        row = await self._get_owned(analysis_id)
        await self._app.delete(row)
        await self._app.flush()

    async def duplicate_analysis(self, analysis_id: UUID) -> SavedAnalysisResponse:
        source = await self._get_owned(analysis_id)
        row = SavedAnalysis(
            user_id=self._user.id,
            industry=self._industry.value,
            title=f"{source.title} (copy)",
            spec=dict(source.spec or {}),
            viz=source.viz,
            sql_snapshot=source.sql_snapshot,
        )
        self._app.add(row)
        await self._app.flush()
        return _to_saved(row)

    async def _get_owned(self, analysis_id: UUID) -> SavedAnalysis:
        row = await self._app.get(SavedAnalysis, analysis_id)
        if row is None or row.user_id != self._user.id or row.industry != self._industry.value:
            raise NotFoundError("Saved analysis not found.")
        return row


# -- assist mapping ---------------------------------------------------------------------

_PLAN_ANALYSIS = {
    "running_total": "running_total",
    "moving_average": "moving_average",
    "period_growth": "period_growth",
    "contribution": "contribution",
    "market_share": "contribution",
    "above_average": "above_average",
    "top_n_per_group": "top_n_per_group",
    "growth_ranking": "growth_contribution",
}
_RELATIVE_PRESETS = {
    "last_month": "last_month",
    "this_month": "this_month",
    "last_quarter": "last_quarter",
    "this_quarter": "this_quarter",
    "ytd": "ytd",
    "fytd": "fytd",
}


def assist_spec(plan: QuestionPlan, catalog: Catalog) -> AnalyticsSpec:
    """Builder fields for a parsed prompt, in catalog ids, adjusted to a valid shape."""
    metric = catalog.metric_for_plan(plan.metric)
    dimensions = [d.id for raw in plan.dimensions if (d := catalog.dimension(raw))]
    dimensions = list(dict.fromkeys(dimensions))
    has_time = any(d in {"month", "quarter", "year"} for d in dimensions)

    analysis = _PLAN_ANALYSIS.get(plan.analysis, "basic")
    if plan.analysis == "ranking":
        if plan.partition_by and len(dimensions) == 2:
            analysis = "top_n_per_group"
        elif not has_time:
            analysis = "top_n" if plan.order_direction == "desc" else "bottom_n"
        else:
            analysis = "ranking"
    elif analysis == "basic" and plan.intent == "trend":
        analysis = "trend"
    if analysis in {"trend", "running_total", "moving_average", "period_growth"} and not has_time:
        dimensions.insert(0, "month")

    filters: list[AnalyticsFilterSpec] = []
    for filt in plan.filters:
        domain = next((d for d in catalog.domains if d.qualified_column == filt.column), None)
        if domain is not None:
            filters.append(AnalyticsFilterSpec(domain=domain.name, values=list(filt.all_values)))
    if len(filters) == 1 and len(filters[0].values) >= 2 and analysis == "basic" and not dimensions:
        dim = next(
            (
                d
                for d in catalog.dimensions
                if (dom := catalog.domain_for_dimension(d.id)) and dom.name == filters[0].domain
            ),
            None,
        )
        if dim is not None:
            dimensions, analysis = [dim.id], "comparison"

    preset = None
    period = plan.period
    if period is not None:
        if period.relative in _RELATIVE_PRESETS:
            preset = _RELATIVE_PRESETS[period.relative]
        elif period.relative == "last_n_months":
            preset = {
                3: "last_3_months",
                6: "last_6_months",
                12: "last_12_months",
                24: "last_24_months",
            }.get(period.count)
        elif period.relative == "last_n_days":
            preset = {7: "last_7_days", 30: "last_30_days"}.get(period.count)
        if preset is None and period.start and period.end:
            return _assist_result(
                metric,
                dimensions,
                filters,
                analysis,
                plan,
                "custom",
                period.start.isoformat(),
                (period.end - timedelta(days=1)).isoformat(),
            )
    elif plan.year_filter:
        year = int(plan.year_filter)
        return _assist_result(
            metric, dimensions, filters, analysis, plan, "custom", f"{year}-01-01", f"{year}-12-31"
        )
    return _assist_result(metric, dimensions, filters, analysis, plan, preset, None, None)


def _assist_result(
    metric: Any,
    dimensions: list[str],
    filters: list[AnalyticsFilterSpec],
    analysis: str,
    plan: QuestionPlan,
    preset: str | None,
    date_from: str | None,
    date_to: str | None,
) -> AnalyticsSpec:
    return AnalyticsSpec(
        metrics=[metric.id] if metric is not None else [],
        dimensions=dimensions,
        filters=filters,
        analysis=analysis,  # type: ignore[arg-type]
        limit=max(1, min(plan.limit or 10, 100)),
        order_direction=plan.order_direction,
        date_preset=preset,
        date_from=date_from,
        date_to=date_to,
    )


# -- charts -----------------------------------------------------------------------------

_USER_VIZ = {
    "bar": "bar",
    "line": "line",
    "area": "area",
    "pie": "pie",
    "donut": "pie",
    "scatter": "scatter",
}


def build_chart(
    query: BuilderQuery, columns: list[str], rows: list[dict[str, Any]], requested: str
) -> tuple[AnalyticsChartPayload | None, AnalyticsVizKind]:
    """Chart payload shaped for the analysis: overlays, pivots for time x category, combined labels."""
    if not rows:
        return None, "table"
    t = query.time_column
    cats = query.category_columns
    value = query.value_column or query.metric_column
    if not t and not cats:
        return None, "kpi"

    chart_type = "line" if t else "bar"
    note: str | None = None
    if query.analysis in {"period_growth", "yoy_growth"}:
        chart_type = "bar" if not cats else "line"
    if query.analysis == "contribution" and not t and len(rows) <= 8:
        chart_type = "pie"

    if t and cats:
        x, series, points, dropped = _pivot(rows, t, cats, value)
        if dropped:
            note = f"Chart shows the top {len(series)} of {len(series) + dropped} by total; the table has all."
        y = series[0] if series else value
    elif t:
        x, points = t, [{k: row.get(k) for k in columns} for row in rows]
        series = [c for c in query.overlay_columns if c in columns] or [value]
        y = series[-1] if query.analysis == "moving_average" else series[0]
        if query.analysis == "running_total":
            series = [value]
            y = value
    else:
        label = "label"
        points = []
        for row in rows:
            point = {k: row.get(k) for k in columns}
            point[label] = (
                " \u00b7 ".join(str(row.get(c)) for c in cats if row.get(c) is not None)
                or "(blank)"
            )
            points.append(point)
        x = label if len(cats) > 1 else cats[0]
        if len(cats) == 1:
            points = [{k: v for k, v in p.items() if k != label} for p in points]
        overlays = [c for c in query.overlay_columns if c in columns]
        series = (
            overlays
            if query.analysis in {"actual_vs_target", "growth_contribution"} and overlays
            else [value]
        )
        y = value if value in columns else series[0]
        if query.analysis == "growth_contribution":
            series, y = [value], value

    if requested in _USER_VIZ:
        wanted = _USER_VIZ[requested]
        if wanted != "pie" or (not t and len(series) <= 1):
            chart_type = wanted
    viz: AnalyticsVizKind = chart_type  # type: ignore[assignment]
    if requested in {"table", "heatmap", "treemap", "kpi"}:
        viz = requested  # type: ignore[assignment]
    return (
        AnalyticsChartPayload(
            type=chart_type,
            x=x,
            y=y,
            series=series if len(series) > 1 else [],
            points=points[:120],
            note=note,
        ),
        viz,
    )


def _pivot(
    rows: list[dict[str, Any]], time_col: str, cat_cols: list[str], value_col: str
) -> tuple[str, list[str], list[dict[str, Any]], int]:
    totals: dict[str, float] = defaultdict(float)
    grid: dict[Any, dict[str, Any]] = {}
    for row in rows:
        key = (
            " \u00b7 ".join(str(row.get(c)) for c in cat_cols if row.get(c) is not None)
            or "(blank)"
        )
        v = row.get(value_col)
        number = float(v) if isinstance(v, (int, float)) else None
        if number is not None:
            totals[key] += abs(number)
        grid.setdefault(row.get(time_col), {time_col: row.get(time_col)})[key] = number
    ordered = sorted(totals, key=lambda k: totals[k], reverse=True)
    series = ordered[:_MAX_SERIES]
    points = [
        {time_col: period, **{s: values.get(s) for s in series}}
        for period, values in sorted(grid.items(), key=lambda kv: str(kv[0]))
    ]
    return time_col, series, points, max(0, len(ordered) - len(series))


# -- helpers ----------------------------------------------------------------------------


def _partial_period(
    query: BuilderQuery, as_of: date | None, rows: list[dict[str, Any]]
) -> str | None:
    """Label of the last period when the data stops before its end (e.g. Sep 2026 through the 12th)."""
    grain = query.time_grain
    if not grain or as_of is None or not rows or not query.time_column:
        return None
    if grain == "month":
        start = as_of.replace(day=1)
        last_day = calendar.monthrange(as_of.year, as_of.month)[1]
        complete = as_of.day == last_day
    elif grain == "quarter":
        first_month = 3 * ((as_of.month - 1) // 3) + 1
        start = date(as_of.year, first_month, 1)
        end_month = first_month + 2
        complete = as_of == date(
            as_of.year, end_month, calendar.monthrange(as_of.year, end_month)[1]
        )
    else:
        start = date(as_of.year, 1, 1)
        complete = as_of.month == 12 and as_of.day == 31
    if complete:
        return None
    last = max(str(r.get(query.time_column) or "") for r in rows)
    expected = str(start.year) if grain == "year" else start.isoformat()
    if not last.startswith(expected):
        return None
    return period_name(start, grain)


def _shift(start: date, grain: str, step: int) -> date:
    months = {"month": 1, "quarter": 3, "year": 12}.get(grain, 1) * step
    total = start.year * 12 + start.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def _friendly_failure(exc: Exception) -> str:
    message = str(exc).lower()
    if "statement timeout" in message or "canceling statement" in message:
        return (
            "This analysis took too long to run. Narrow the date range, add a filter, or use fewer "
            "dimensions, then try again."
        )
    if "connection" in message or "could not connect" in message:
        return "The data source is unavailable right now. Please try again in a moment."
    return (
        "The data source couldn't complete this analysis. Try a simpler selection or one of the "
        "suggested analyses; the issue has been logged for the data team."
    )


def _to_saved(row: SavedAnalysis) -> SavedAnalysisResponse:
    return SavedAnalysisResponse(
        id=row.id,
        title=row.title,
        industry=row.industry,
        spec=dict(row.spec or {}),
        viz=row.viz,
        sql_snapshot=row.sql_snapshot,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")
