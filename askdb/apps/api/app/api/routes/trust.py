"""Data Trust Center routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
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
from app.schemas.trust import (
    DataTrustCenterResponse,
    StewardFeedbackRequest,
    UpdateRuleThresholdRequest,
)
from app.semantic.service import SemanticService
from app.services.trust import (
    DataTrustService,
    clear_trust_cache,
    get_shared_trust_snapshot,
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


@router.get("/center", response_model=DataTrustCenterResponse)
async def trust_center(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
    refresh: bool = Query(default=False),
) -> DataTrustCenterResponse:
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


@router.get("/snapshot")
async def trust_snapshot(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    semantic: SemanticDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Shared trust signal for Chat + Executive Intelligence."""
    del user
    cached = get_shared_trust_snapshot(industry.value)
    if cached and cached.get("score") is not None:
        return {"available": True, **cached}
    service = DataTrustService(
        connection=connection,
        semantic=semantic,
        settings=settings,
        industry=industry,
    )
    center = await service.get_center()
    return {
        "available": center.hero.available,
        "score": center.hero.score,
        "label": center.hero.label,
        "components": [c.model_dump(by_alias=True) for c in center.hero.components],
        "formulaNote": center.hero.formula_note,
        "activeIncidents": center.hero.active_incidents,
        "computedAt": center.computed_at,
    }


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
    session: Annotated[AsyncSession, Depends(get_app_session)],
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
