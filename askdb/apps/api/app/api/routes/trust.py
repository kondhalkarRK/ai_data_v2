"""Data Trust Center routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAdmin,
    RequireUser,
    get_app_session,
    get_app_settings,
    get_scoped_analytics,
    get_semantic_service,
)
from app.core.config import Settings
from app.models.enums import Role
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
from app.services.governance.audit import AdminAction, record_admin_action
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

AnalyticsConnection = Annotated[AsyncConnection, Depends(get_scoped_analytics)]
SemanticDep = Annotated[SemanticService, Depends(get_semantic_service)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_app_session)]


@router.get("/center", response_model=DataTrustCenterResponse)
async def trust_center(
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    refresh: bool = Query(default=False),
) -> DataTrustCenterResponse:
    """Legacy profiling view (sample-based); the Trust Center UI uses ``/trust/reliability``."""
    refresh = refresh and user.role is Role.ADMIN
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
    user: RequireUser,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    session: SessionDep,
    refresh: bool = Query(default=False),
) -> DataReliabilityResponse:
    service = DataReliabilityService(
        connection=connection, semantic=semantic, industry=industry, app_session=session
    )
    if refresh and user.role is Role.ADMIN:
        await record_admin_action(
            session, user.id, AdminAction.REFRESHED_TRUST_SCORES, f"Industry: {industry.value}"
        )
        return await service.center(refresh=True, user=user.email)
    return await service.center(refresh=False, user=user.email)


@router.post(
    "/reliability/monitors",
    response_model=MonitorMutationResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitor(
    body: CreateMonitorRequest,
    user: RequireAdmin,
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
    user: RequireAdmin,
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
    if body.enabled is not None:
        await record_admin_action(
            session,
            user.id,
            AdminAction.ENABLED_DQ_RULE if body.enabled else AdminAction.DISABLED_DQ_RULE,
            f"Rule: {rule_id} ({industry.value})",
        )
    return result


@router.post("/reliability/monitors/bulk", response_model=MonitorMutationResult)
async def bulk_update_monitors(
    body: BulkMonitorRequest,
    user: RequireAdmin,
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
    user: RequireAdmin,
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
    user: RequireUser,
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
    user: RequireAdmin,
    industry: ActiveIndustry,
) -> dict[str, Any]:
    del user, industry
    return update_rule_threshold(rule_id, body.threshold)


@router.post("/steward/feedback")
async def steward_feedback(
    body: StewardFeedbackRequest,
    user: RequireUser,
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
