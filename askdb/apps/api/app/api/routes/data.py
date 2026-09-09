"""Data Preview and Data Quality routes."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    ActiveIndustry,
    RequireViewer,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Settings
from app.db.session import DatabaseRegistry
from app.schemas.data import DataQualityReport, PreviewPage, PreviewTableSummary
from app.semantic.service import SemanticService
from app.services.data_preview import DataPreviewService
from app.services.data_quality import DataQualityService

router = APIRouter(prefix="/data", tags=["data"])


async def get_analytics_connection(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


AnalyticsConnection = Annotated[AsyncConnection, Depends(get_analytics_connection)]
SemanticDep = Annotated[SemanticService, Depends(get_semantic_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get(
    "/tables",
    response_model=list[PreviewTableSummary],
    summary="List previewable tables for the active industry",
)
async def list_tables(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
) -> list[PreviewTableSummary]:
    service = DataPreviewService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    return await service.list_tables()


@router.get(
    "/preview/{table_name}",
    response_model=PreviewPage,
    summary="Keyset-paginated preview of a semantic table",
)
async def preview_table(
    table_name: str,
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    cursor: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
) -> PreviewPage:
    service = DataPreviewService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    return await service.preview_rows(table_name, cursor=cursor, limit=limit)


@router.get(
    "/quality/{table_name}",
    response_model=DataQualityReport,
    summary="Data-quality score for a semantic table sample",
)
async def data_quality(
    table_name: str,
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    sample_rows: int | None = Query(default=None, ge=100, le=10_000),
) -> DataQualityReport:
    service = DataQualityService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    return await service.evaluate(table_name, sample_rows=sample_rows)


@router.get(
    "/export/{table_name}",
    summary="CSV export of a capped preview page",
)
async def export_table(
    table_name: str,
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    cursor: str | None = Query(default=None),
) -> StreamingResponse:
    service = DataPreviewService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    page = await service.preview_rows(table_name, cursor=cursor, limit=None)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    headers = [column.name for column in page.columns]
    writer.writerow(headers)
    for row in page.items:
        writer.writerow([row.values.get(name, "") for name in headers])
    buffer.seek(0)
    filename = f"{industry.value}-{table_name}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
