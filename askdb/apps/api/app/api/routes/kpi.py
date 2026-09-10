"""KPI / executive dashboard routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    ActiveIndustry,
    RequireViewer,
    get_registry,
)
from app.db.session import DatabaseRegistry
from app.schemas.kpi import (
    KpiFilterOptions,
    KpiSummaryResponse,
    ScenarioRequest,
    ScenarioResponse,
    WindowId,
)
from app.services.kpi import KpiService

router = APIRouter(prefix="/kpis", tags=["kpis"])


async def get_analytics_connection(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


AnalyticsConnection = Annotated[AsyncConnection, Depends(get_analytics_connection)]


@router.get("/filters", response_model=KpiFilterOptions)
async def kpi_filters(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> KpiFilterOptions:
    return await KpiService(connection, industry).filter_options()


@router.get("/summary", response_model=KpiSummaryResponse)
async def kpi_summary(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
    compare: bool = Query(default=True),
) -> KpiSummaryResponse:
    return await KpiService(connection, industry).summary(
        window=window,
        lob=lob,
        region=region,
        make=make,
        as_of=as_of,
        compare=compare,
    )


@router.get("/export")
async def kpi_export(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
) -> PlainTextResponse:
    csv_text = await KpiService(connection, industry).export_csv(
        window=window, lob=lob, region=region, make=make, as_of=as_of
    )
    filename = f"nql-{industry.value}-kpis-{window}.csv"
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/scenario", response_model=ScenarioResponse)
async def kpi_scenario(
    body: ScenarioRequest,
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> ScenarioResponse:
    return await KpiService(connection, industry).scenario(body)
