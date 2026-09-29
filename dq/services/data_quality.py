"""Data quality evaluation against analytics tables."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.analytics.data_quality import compute_data_quality
from app.analytics.sql_guardrails import qualify_ident, qualify_table, sql_is_safe
from app.core.config import Industry, Settings
from app.core.exceptions import GuardrailViolationError, NotFoundError
from app.schemas.data import DataQualityReport
from app.semantic.service import SemanticService


class DataQualityService:
    def __init__(
        self,
        *,
        connection: AsyncConnection,
        semantic: SemanticService,
        settings: Settings,
        industry: Industry,
    ) -> None:
        self._connection = connection
        self._semantic = semantic
        self._settings = settings
        self._industry = industry

    async def evaluate(
        self, table_name: str, *, sample_rows: int | None = None
    ) -> DataQualityReport:
        pack = await self._semantic.get_pack(self._industry)
        table = pack.model.tables.get(table_name)
        if table is None:
            raise NotFoundError(f"Unknown table '{table_name}'.")

        schema, _, physical = table.physical_name.partition(".")
        if not physical:
            schema, physical = self._industry.value, table.physical_name
        qualified = qualify_table(schema, physical)
        pk = qualify_ident(table.primary_key)
        limit = min(
            sample_rows or min(5_000, self._settings.sql_max_result_rows),
            self._settings.sql_max_result_rows,
        )
        sql = f"SELECT * FROM {qualified} ORDER BY {pk} DESC LIMIT :limit"  # noqa: S608
        ok, reason = sql_is_safe(sql)
        if not ok:
            raise GuardrailViolationError(reason)

        result = await self._connection.execute(text(sql), {"limit": limit})
        rows: list[dict[str, Any]] = [dict(row) for row in result.mappings().all()]
        report = compute_data_quality(rows)
        return DataQualityReport(
            table=table_name,
            physical_name=table.physical_name,
            sample_rows=len(rows),
            health_score=report["health_score"],
            total_rows=report["total_rows"],
            total_cols=report["total_cols"],
            total_null_pct=report["total_null_pct"],
            duplicate_count=report["duplicate_count"],
            duplicate_pct=report["duplicate_pct"],
            null_summary=report["null_summary"],
            outliers=report["outliers"],
            type_issues=report["type_issues"],
            cardinality_flags=report["cardinality_flags"],
            date_gaps=report["date_gaps"],
            date_col=report.get("date_col"),
            computed_in=report.get("computed_in", "python"),
        )
