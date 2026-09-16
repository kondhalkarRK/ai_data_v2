"""Analytics Builder API — structured business analytics over the semantic layer."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAnalyst,
    get_app_session,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Settings
from app.db.session import DatabaseRegistry
from app.schemas.analytics import (
    AnalyticsAssistRequest,
    AnalyticsAssistResponse,
    AnalyticsRunRequest,
    AnalyticsRunResponse,
    FilterValuesResponse,
    SavedAnalysisCreate,
    SavedAnalysisResponse,
    SavedAnalysisUpdate,
)
from app.semantic.service import SemanticService
from app.services.analytics.runner import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _analytics_conn(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


def _service(
    user: RequireAnalyst,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(_analytics_conn)],
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> AnalyticsService:
    return AnalyticsService(
        app_session=session,
        analytics=analytics,
        settings=settings,
        user=user,
        industry=industry,
        semantic_service=semantic_service,
    )


AnalyticsServiceDep = Annotated[AnalyticsService, Depends(_service)]


@router.post("/run", response_model=AnalyticsRunResponse, summary="Run a structured analysis")
async def run_analysis(
    body: AnalyticsRunRequest,
    service: AnalyticsServiceDep,
) -> AnalyticsRunResponse:
    return await service.run(body.spec)


@router.post(
    "/assist",
    response_model=AnalyticsAssistResponse,
    summary="Populate builder fields from a natural-language prompt",
)
async def assist_builder(
    body: AnalyticsAssistRequest,
    service: AnalyticsServiceDep,
) -> AnalyticsAssistResponse:
    return await service.assist(body)


@router.get(
    "/filter-values",
    response_model=FilterValuesResponse,
    summary="Distinct filter values from the value dictionary",
)
async def filter_values(
    service: AnalyticsServiceDep,
    domain: str = Query(min_length=1, max_length=80),
    q: str | None = Query(default=None, max_length=120),
    parent_domain: str | None = Query(default=None, max_length=80),
    parent_values: list[str] | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
) -> FilterValuesResponse:
    return await service.filter_values(
        domain,
        q=q,
        parent_domain=parent_domain,
        parent_values=parent_values,
        limit=limit,
    )


@router.get("/analyses", response_model=list[SavedAnalysisResponse])
async def list_analyses(service: AnalyticsServiceDep) -> list[SavedAnalysisResponse]:
    return await service.list_analyses()


@router.post("/analyses", response_model=SavedAnalysisResponse, status_code=201)
async def create_analysis(
    body: SavedAnalysisCreate,
    service: AnalyticsServiceDep,
) -> SavedAnalysisResponse:
    return await service.create_analysis(body)


@router.patch("/analyses/{analysis_id}", response_model=SavedAnalysisResponse)
async def update_analysis(
    analysis_id: uuid.UUID,
    body: SavedAnalysisUpdate,
    service: AnalyticsServiceDep,
) -> SavedAnalysisResponse:
    return await service.update_analysis(analysis_id, body)


@router.post("/analyses/{analysis_id}/duplicate", response_model=SavedAnalysisResponse)
async def duplicate_analysis(
    analysis_id: uuid.UUID,
    service: AnalyticsServiceDep,
) -> SavedAnalysisResponse:
    return await service.duplicate_analysis(analysis_id)


@router.delete("/analyses/{analysis_id}", status_code=204)
async def delete_analysis(
    analysis_id: uuid.UUID,
    service: AnalyticsServiceDep,
) -> None:
    await service.delete_analysis(analysis_id)
