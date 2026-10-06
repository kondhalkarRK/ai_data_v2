"""KPI / executive dashboard routes."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncConnection

from app.api.deps import (
    ActiveIndustry,
    RegionScopeDep,
    RequireUser,
    get_scoped_analytics,
)
from app.schemas.kpi import (
    KpiFilterOptions,
    KpiSummaryResponse,
    ScenarioRequest,
    ScenarioResponse,
    WindowId,
)
from app.services.kpi import KpiService
from app.services.security.region_scope import assert_requested_region

router = APIRouter(prefix="/kpis", tags=["kpis"])

AnalyticsConnection = Annotated[AsyncConnection, Depends(get_scoped_analytics)]


@router.get("/filters", response_model=KpiFilterOptions)
async def kpi_filters(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> KpiFilterOptions:
    return await KpiService(connection, industry).filter_options()


@router.get("/summary", response_model=KpiSummaryResponse)
async def kpi_summary(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    scope: RegionScopeDep,
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
    compare: bool = Query(default=True),
) -> KpiSummaryResponse:
    assert_requested_region(scope, region)
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
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    scope: RegionScopeDep,
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    as_of: date | None = Query(default=None),
) -> PlainTextResponse:
    assert_requested_region(scope, region)
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
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> ScenarioResponse:
    return await KpiService(connection, industry).scenario(body)
