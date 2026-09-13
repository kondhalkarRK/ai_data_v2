"""Executive Intelligence routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireViewer,
    get_app_session,
    get_registry,
)
from app.db.session import DatabaseRegistry
from app.models.activity import InsightFeedback
from app.schemas.executive import (
    ExecutiveIntelligenceResponse,
    InsightFeedbackRequest,
    InsightFeedbackResponse,
)
from app.schemas.kpi import WindowId
from app.services.executive import ExecutiveIntelligenceService, clear_executive_cache

router = APIRouter(prefix="/executive", tags=["executive"])


async def get_analytics_connection(
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
) -> AsyncIterator[AsyncConnection]:
    async with registry.analytics_connection(industry) as connection:
        yield connection


AnalyticsConnection = Annotated[AsyncConnection, Depends(get_analytics_connection)]


@router.get("/intelligence", response_model=ExecutiveIntelligenceResponse)
async def executive_intelligence(
    user: RequireViewer,
    industry: ActiveIndustry,
    connection: AnalyticsConnection,
    window: WindowId = Query(default="ytd"),
    lob: str | None = Query(default=None),
    region: str | None = Query(default=None),
    make: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> ExecutiveIntelligenceResponse:
    del user  # Auth gate only; same warehouse ACLs as KPI/chat readers.
    if refresh:
        clear_executive_cache()
    service = ExecutiveIntelligenceService(connection=connection, industry=industry)
    return await service.get_bundle(
        window=window,
        lob=lob,
        region=region,
        make=make,
        force_refresh=refresh,
    )


@router.post("/insights/feedback", response_model=InsightFeedbackResponse)
async def insight_feedback(
    body: InsightFeedbackRequest,
    user: RequireViewer,
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
