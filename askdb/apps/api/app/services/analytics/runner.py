"""Execute Analytics Builder specs via the semantic compiler."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Industry, Settings
from app.core.exceptions import NotFoundError, NqlError
from app.models.activity import SavedAnalysis
from app.models.user import User
from app.schemas.analytics import (
    AnalyticsAssistRequest,
    AnalyticsAssistResponse,
    AnalyticsChartPayload,
    AnalyticsInsights,
    AnalyticsRunResponse,
    AnalyticsSpec,
    FilterValueItem,
    FilterValuesResponse,
    SavedAnalysisCreate,
    SavedAnalysisResponse,
    SavedAnalysisUpdate,
)
from app.semantic.service import SemanticService
from app.services.analytics.chart_recommend import recommend_viz
from app.services.analytics.spec_to_plan import (
    AnalyticsSpecError,
    plan_to_builder_spec,
    spec_to_plan,
)
from app.services.chat.question_understanding import understand_question
from app.services.chat.response_meta import build_insights
from app.services.chat.semantic_analytics import (
    SemanticCompileError,
    compile_analytical_query,
)
from app.services.chat.templates import resolve_template
from app.services.chat.value_dictionary import BusinessValue, domains_for, get_value_dictionary

logger = logging.getLogger(__name__)


class AnalyticsRunError(NqlError):
    status_code = 422
    code = "analytics_run_failed"
    message = "The analysis could not be executed."


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


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

    async def run(self, spec: AnalyticsSpec) -> AnalyticsRunResponse:
        pack = await self._semantic.get_pack(self._industry)
        plan = spec_to_plan(spec, self._industry, pack)
        recommended = recommend_viz(spec)

        sql_text: str | None = None
        title = "Analysis"
        path = "semantic_compiler"

        try:
            if plan.dimensions:
                compiled = compile_analytical_query(plan, pack, force=True)
                if compiled is not None:
                    sql_text = compiled.sql
                    title = compiled.title
                else:
                    hit = resolve_template(
                        self._industry,
                        _synthetic_question(spec),
                        plan=plan,
                        pack=pack,
                    )
                    if hit is not None:
                        sql_text = hit.sql
                        title = hit.title
                        path = hit.path
            else:
                sql_text, title = _compile_kpi_sql(plan, pack)
                path = "kpi_aggregate"
        except (SemanticCompileError, AnalyticsSpecError) as exc:
            raise AnalyticsRunError(str(exc)) from exc

        if not sql_text:
            raise AnalyticsRunError(
                "Could not compile this analysis against the active semantic pack. "
                "Try fewer dimensions or a different metric."
            )

        try:
            await self._analytics.execute(text("SET TRANSACTION READ ONLY"))
            timeout_ms = int(self._settings.nlq_sql_timeout_seconds * 1000)
            await self._analytics.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            result = await self._analytics.execute(text(sql_text))
            mappings = result.mappings().all()
            cap = min(self._settings.nlq_default_result_limit, self._settings.sql_max_result_rows)
            capped = mappings[:cap]
            columns = list(capped[0].keys()) if capped else list(result.keys())
            rows = [{key: _jsonable(value) for key, value in row.items()} for row in capped]
        except Exception as exc:
            logger.exception("Analytics Builder SQL failed")
            raise AnalyticsRunError(
                "The warehouse could not execute this analysis.",
                details={"cause": str(exc)[:240]},
            ) from exc

        chart = None
        if rows and len(columns) >= 2 and recommended != "kpi":
            chart = AnalyticsChartPayload(
                type="pie" if recommended in {"pie", "donut"} else (
                    "line" if recommended in {"line", "area"} else (
                        "scatter" if recommended == "scatter" else "bar"
                    )
                ),
                x=columns[0],
                y=columns[1] if len(columns) > 1 else columns[0],
                points=rows[:40],
            )

        insight_payload = build_insights(
            narrative=title,
            columns=columns,
            rows=rows,
            path=path,
        )
        insights = AnalyticsInsights(
            executive=insight_payload["executive"],
            analyst=insight_payload["analyst"],
        )

        return AnalyticsRunResponse(
            title=title,
            columns=columns,
            rows=rows,
            sql=sql_text,
            chart=chart,
            recommended_viz=recommended,
            insights=insights,
            meta={
                "path": path,
                "metric": plan.metric,
                "dimensions": plan.dimensions,
                "analysis": plan.analysis,
                "rowCount": len(rows),
            },
        )

    async def assist(self, body: AnalyticsAssistRequest) -> AnalyticsAssistResponse:
        pack = await self._semantic.get_pack(self._industry)
        dictionary = await get_value_dictionary(
            self._analytics, self._industry, pack=pack
        )
        value_filters = dictionary.match(body.prompt)
        plan = understand_question(
            self._industry,
            body.prompt,
            value_filters=value_filters,
        )
        spec = plan_to_builder_spec(plan, pack)
        bits = []
        if spec.metrics:
            bits.append(f"Metric: {', '.join(spec.metrics)}")
        if spec.dimensions:
            bits.append(f"Dimensions: {', '.join(spec.dimensions)}")
        if spec.filters:
            bits.append(
                "Filters: "
                + ", ".join(f"{f.domain}={','.join(f.values)}" for f in spec.filters)
            )
        if spec.analysis != "basic":
            bits.append(f"Analysis: {spec.analysis}")
        explanation = (
            "Populated from your prompt using the semantic layer and value dictionary. "
            + (" · ".join(bits) if bits else "Adjust the fields and run.")
        )
        return AnalyticsAssistResponse(
            spec=spec,
            explanation=explanation,
            glossary_hits=list(plan.glossary_hits),
        )

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
        dictionary = await get_value_dictionary(
            self._analytics, self._industry, pack=pack
        )
        domains = domains_for(self._industry, pack)
        needle = domain.strip().casefold()
        matched = None
        for item in domains:
            leaf = item.column.split(".")[-1].casefold()
            if needle in {
                item.name.casefold(),
                item.label.casefold(),
                leaf,
                domain.casefold(),
            }:
                matched = item
                break
            if needle.replace(" ", "_") == leaf:
                matched = item
                break
        if matched is None:
            raise AnalyticsSpecError(
                f"Unknown filter domain '{domain}'.",
                details={"domain": domain},
            )

        values = [
            v
            for v in dictionary.values
            if v.column == matched.qualified_column
            or v.domain.casefold() == matched.name.casefold()
        ]

        # Cascading: when parent filters provided on the same table, re-query distincts.
        if parent_domain and parent_values:
            parent = None
            pneedle = parent_domain.strip().casefold()
            for item in domains:
                leaf = item.column.split(".")[-1].casefold()
                if pneedle in {item.name.casefold(), item.label.casefold(), leaf}:
                    parent = item
                    break
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

        return FilterValuesResponse(domain=domain, label=matched.label, values=items)

    async def list_analyses(self) -> list[SavedAnalysisResponse]:
        rows = (
            await self._app.execute(
                select(SavedAnalysis)
                .where(SavedAnalysis.user_id == self._user.id)
                .where(SavedAnalysis.industry == self._industry.value)
                .order_by(SavedAnalysis.updated_at.desc())
            )
        ).scalars().all()
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
        if (
            row is None
            or row.user_id != self._user.id
            or row.industry != self._industry.value
        ):
            raise NotFoundError("Saved analysis not found.")
        return row


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


def _synthetic_question(spec: AnalyticsSpec) -> str:
    parts = []
    if spec.metrics:
        parts.append(spec.metrics[0].replace("_", " "))
    if spec.dimensions:
        parts.append("by " + " and ".join(d.replace("_", " ") for d in spec.dimensions))
    for filt in spec.filters:
        if filt.values:
            parts.append(f"for {filt.values[0]}")
    return " ".join(parts) or "revenue"


def _compile_kpi_sql(plan: Any, pack: Any) -> tuple[str, str]:
    """Single-metric aggregate with optional filters — no GROUP BY."""
    from app.services.chat.semantic_analytics import (
        _ALIASES,
        _join_clauses,
        _metric_spec,
        _where_clauses,
    )

    metric = _metric_spec(plan)
    tables = getattr(getattr(pack, "model", None), "tables", {}) or {}
    physical = getattr(tables.get(metric.table), "physical_name", metric.table)
    alias = _ALIASES.get(metric.table, "f")
    expression = metric.expression.format(alias=alias)
    required: set[str] = set()
    where = _where_clauses(plan, pack, required)
    joins = _join_clauses(pack, metric.table, required)
    join_sql = ("\n" + "\n".join(joins)) if joins else ""
    where_sql = f"\nWHERE {' AND '.join(where)}" if where else ""
    sql = (
        f"SELECT {expression} AS {metric.alias}\n"
        f"FROM {physical} AS {alias}"
        f"{join_sql}"
        f"{where_sql}\n"
        f"LIMIT {int(plan.limit)}"
    )
    title = metric.alias.replace("_", " ").title()
    return sql.strip(), title
