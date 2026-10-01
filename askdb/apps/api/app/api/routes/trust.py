"""Data Trust Center routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAnalyst,
    RequireViewer,
    get_app_session,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Settings
from app.db.session import DatabaseRegistry
from app.schemas.reliability import (
    BulkMonitorRequest,
    CreateMonitorRequest,
    DataReliabilityResponse,
    MonitorMutationResult,
    UpdateMonitorRequest,
)
from app.schemas.trust import (
    DataTrustCenterResponse,
    StewardFeedbackRequest,
    UpdateRuleThresholdRequest,
)
from app.semantic.service import SemanticService
from app.services.reliability import (
    DataReliabilityService,
    MonitorValidationError,
    shared_snapshot,
)
from app.services.trust import (
    DataTrustService,
    clear_trust_cache,
    update_rule_threshold,
)

router = APIRouter(prefix="/trust", tags=["trust"])


async def get_analytics_connection(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


AnalyticsConnection = Annotated[AsyncConnection, Depends(get_analytics_connection)]
SemanticDep = Annotated[SemanticService, Depends(get_semantic_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_app_session)]


@router.get("/center", response_model=DataTrustCenterResponse)
async def trust_center(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    refresh: bool = Query(default=False),
) -> DataTrustCenterResponse:
    """Legacy profiling view (sample-based); the Trust Center UI uses ``/trust/reliability``."""
    del user
    if refresh:
        clear_trust_cache()
    service = DataTrustService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    return await service.get_center(force_refresh=refresh)


@router.get("/reliability", response_model=DataReliabilityResponse)
async def reliability_center(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    session: SessionDep,
    refresh: bool = Query(default=False),
) -> DataReliabilityResponse:
    service = DataReliabilityService(
        connection=connection, semantic=semantic, industry=industry, app_session=session
    )
    return await service.center(refresh=refresh, user=user.email)


@router.post(
    "/reliability/monitors",
    response_model=MonitorMutationResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitor(
    body: CreateMonitorRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
) -> MonitorMutationResult:
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    try:
        return await service.create_monitor(body, user.email)
    except MonitorValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/reliability/monitors/{rule_id}", response_model=MonitorMutationResult)
async def update_monitor(
    rule_id: str,
    body: UpdateMonitorRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
) -> MonitorMutationResult:
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    result = await service.update_monitor(rule_id, body, user.email)
    if not result.ok and rule_id in result.skipped:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found.")
    return result


@router.post("/reliability/monitors/bulk", response_model=MonitorMutationResult)
async def bulk_update_monitors(
    body: BulkMonitorRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
) -> MonitorMutationResult:
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    return await service.bulk(body, user.email)


@router.delete("/reliability/monitors/{rule_id}", response_model=MonitorMutationResult)
async def delete_monitor(
    rule_id: str,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
) -> MonitorMutationResult:
    del user
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    result = await service.delete_monitor(rule_id)
    if not result.ok:
        raise HTTPException(status.HTTP_409_CONFLICT, result.message or "Cannot delete this rule.")
    return result


@router.get("/snapshot")
async def trust_snapshot(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    session: SessionDep,
) -> dict[str, Any]:
    """Shared trust signal for Chat + Executive Intelligence (same score as the Trust Center)."""
    cached = shared_snapshot(industry.value)
    if cached is None:
        service = DataReliabilityService(
            connection=connection, semantic=semantic, industry=industry, app_session=session
        )
        await service.center(user=user.email)
        cached = shared_snapshot(industry.value)
    if not cached or cached.get("score") is None:
        return {"available": False, "score": None, "label": "Not measured", "components": []}
    return {"available": True, **cached}


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    body: UpdateRuleThresholdRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
) -> dict[str, Any]:
    del user, industry
    return update_rule_threshold(rule_id, body.threshold)


@router.post("/steward/feedback")
async def steward_feedback(
    body: StewardFeedbackRequest,
    user: RequireViewer,
    industry: ActiveIndustry,
    session: SessionDep,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    service = DataTrustService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
        app_session=session,
    )
    feedback_id = await service.record_steward_feedback(
        user_id=user.id,
        vote=body.vote,
        grounded_on=body.grounded_on,
        body_preview=body.body_preview,
    )
    return {"ok": True, "id": feedback_id}
