"""Executive Intelligence routes."""

from __future__ import annotations

import time
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RegionScopeDep,
    RequireUser,
    get_app_session,
    get_app_settings,
    get_scoped_analytics,
)
from app.core.config import Industry, Settings
from app.models.activity import InsightFeedback
from app.schemas.executive import (
    ExecutiveIntelligenceResponse,
    InsightFeedbackRequest,
    InsightFeedbackResponse,
)
from app.schemas.executive_cockpit import CockpitOptions, CockpitResponse
from app.schemas.kpi import WindowId
from app.services.executive import ExecutiveIntelligenceService, clear_executive_cache
from app.services.executive.cockpit import (
    CockpitFilters,
    ExecutiveCockpitService,
    clear_cockpit_cache,
    fetch_cockpit_options,
)
from app.services.executive.dashboard import QueryMeter, register_dashboard, semantic_revision
from app.services.executive.region_map import (
    DealerMapRow,
    ModelMapRow,
    RegionMapPoint,
    fetch_dealer_models,
    fetch_region_dealers,
    fetch_region_map,
)
from app.services.security.region_scope import assert_requested_region

router = APIRouter(prefix="/executive", tags=["executive"])

AnalyticsConnection = Annotated[AsyncConnection, Depends(get_scoped_analytics)]


@router.get("/intelligence", response_model=ExecutiveIntelligenceResponse)
async def executive_intelligence(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    scope: RegionScopeDep,
    settings: Annotated[Settings, Depends(get_app_settings)],
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> ExecutiveIntelligenceResponse:
    started = time.perf_counter()
    assert_requested_region(scope, region)
    if refresh:
        clear_executive_cache()
    meter = QueryMeter(connection)
    revision = (
        semantic_revision(settings, industry) if settings.ask_me_augmented_dashboard_enabled else ""
    )
    service = ExecutiveIntelligenceService(
        connection=cast(AsyncConnection, meter), industry=industry
    )
    result = await service.get_bundle(
        window=window,
        lob=lob,
        region=region,
        make=make,
        force_refresh=refresh,
        scope_key=f"{scope.cache_key()}|{revision}",
    )
    if settings.ask_me_augmented_dashboard_enabled:
        result.augmentation = register_dashboard(
            result,
            settings=settings,
            industry=industry,
            user=user,
            scope=scope,
            meter=meter,
            started=started,
            revision=revision,
            filters={
                k: v
                for k, v in {"window": window, "lob": lob, "region": region, "make": make}.items()
                if v
            },
        )
    return result


@router.get("/cockpit", response_model=CockpitResponse)
async def executive_cockpit(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    scope: RegionScopeDep,
    settings: Annotated[Settings, Depends(get_app_settings)],
    year: int | None = Query(default=None, ge=2000, le=2100),
    quarter: int | None = Query(default=None, ge=1, le=4),
    month: int | None = Query(default=None, ge=1, le=12),
    make: str | None = Query(default=None, max_length=80),
    model: str | None = Query(default=None, max_length=80),
    engine_type: str | None = Query(default=None, max_length=40),
    car_type: str | None = Query(default=None, max_length=40),
    zone: str | None = Query(default=None, max_length=40),
    state: str | None = Query(default=None, max_length=10),
    city: str | None = Query(default=None, max_length=80),
    dealer_id: int | None = Query(default=None),
    sales_person_id: int | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> CockpitResponse:
    started = time.perf_counter()
    if industry != Industry.AUTOMOTIVE:
        raise HTTPException(status_code=404, detail="The KPI cockpit is available for automotive.")
    assert_requested_region(scope, zone)
    assert_requested_region(scope, state)
    assert_requested_region(scope, city)
    filters = CockpitFilters(
        year=year, quarter=quarter, month=month, make=make, model=model,
        engine_type=engine_type, car_type=car_type, zone=zone, state=state, city=city,
        dealer_id=dealer_id, sales_person_id=sales_person_id,
    )  # fmt: skip
    if refresh:
        clear_cockpit_cache()
    meter = QueryMeter(connection)
    revision = (
        semantic_revision(settings, industry) if settings.ask_me_augmented_dashboard_enabled else ""
    )
    result = (
        await ExecutiveCockpitService(cast(AsyncConnection, meter)).get_cockpit(
            filters, force_refresh=refresh, scope_key=f"{scope.cache_key()}|{revision}"
        )
    ).model_copy(deep=True)
    if settings.ask_me_augmented_dashboard_enabled:
        result.augmentation = register_dashboard(
            result,
            settings=settings,
            industry=industry,
            user=user,
            scope=scope,
            meter=meter,
            started=started,
            revision=revision,
            filters={k: str(v) for k, v in filters.__dict__.items() if v is not None},
        )
    return result


@router.get("/cockpit/options", response_model=CockpitOptions)
async def executive_cockpit_options(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    scope: RegionScopeDep,
    dealer_id: int | None = Query(default=None),
) -> CockpitOptions:
    del user
    if industry != Industry.AUTOMOTIVE:
        raise HTTPException(status_code=404, detail="The KPI cockpit is available for automotive.")
    return await fetch_cockpit_options(connection, dealer_id=dealer_id, scope_key=scope.cache_key())


@router.get("/region-map", response_model=list[RegionMapPoint])
async def region_map(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    metric: str = Query(default="units"),
) -> list[RegionMapPoint]:
    del user
    return await fetch_region_map(connection, industry, metric=metric)


@router.get("/region-map/{region_id}/dealers", response_model=list[DealerMapRow])
async def region_dealers(
    region_id: int,
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> list[DealerMapRow]:
    del user
    return await fetch_region_dealers(connection, industry, region_id=region_id)


@router.get("/dealers/{dealer_id}/models", response_model=list[ModelMapRow])
async def dealer_models(
    dealer_id: int,
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
) -> list[ModelMapRow]:
    del user
    return await fetch_dealer_models(connection, industry, dealer_id=dealer_id)


@router.post("/insights/feedback", response_model=InsightFeedbackResponse)
async def insight_feedback(
    body: InsightFeedbackRequest,
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
) -> InsightFeedbackResponse:
    row = InsightFeedback(
        id=uuid.uuid4(),
        user_id=user.id,
        industry=industry.value,
        insight_id=body.insight_id[:120],
        vote=body.vote,
        category=body.category,
        grounded_on=body.grounded_on,
        body_preview=(body.body_preview or "")[:500] or None,
    )
    session.add(row)
    await session.flush()
    return InsightFeedbackResponse(ok=True, id=str(row.id))
