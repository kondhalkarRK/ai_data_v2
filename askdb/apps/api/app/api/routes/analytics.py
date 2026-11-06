"""Analytics Builder API — structured business analytics over the semantic layer."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireUser,
    get_app_session,
    get_app_settings,
    get_registry,
    get_scoped_analytics,
    get_semantic_service,
    verify_csrf,
)
from app.core.config import Settings
from app.db.session import DatabaseRegistry
from app.models.bi_report import BiReportRecord
from app.schemas.analytics import (
    AnalyticsAssistRequest,
    AnalyticsAssistResponse,
    AnalyticsCapabilities,
    AnalyticsInspection,
    AnalyticsInspectRequest,
    AnalyticsRunRequest,
    AnalyticsRunResponse,
    FilterValueItem,
    FilterValuesResponse,
    SavedAnalysisCreate,
    SavedAnalysisResponse,
    SavedAnalysisUpdate,
)
from app.schemas.analytics_workspace import (
    WorkspaceNarrationRequest,
    WorkspaceNarrationResponse,
    WorkspacePlanResponse,
    WorkspaceRequest,
    WorkspaceRunRequest,
    WorkspaceRunResponse,
    WorkspaceSaved,
    WorkspaceSaveRequest,
)
from app.schemas.bi import (
    BiCreate,
    BiNarration,
    BiNarrationRequest,
    BiReport,
    BiRunRequest,
    BiTurnRequest,
)
from app.semantic.service import SemanticService
from app.services.analytics.bi import execution as bi_execution
from app.services.analytics.bi import repository as bi_repository
from app.services.analytics.bi.service import turn as bi_turn
from app.services.analytics.runner import AnalyticsService, capabilities_for, inspect_spec
from app.services.analytics.workspace import (
    get_workspace,
    list_workspaces,
    narrate_workspace,
    plan_workspace,
    run_panel,
    save_workspace,
)
from app.services.security.region_scope import RegionScope, zone_for_label

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _service(
    user: RequireUser,
    industry: ActiveIndustry,
    session: Annotated[AsyncSession, Depends(get_app_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    analytics: Annotated[AsyncConnection, Depends(get_scoped_analytics)],
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


@router.get("/bi/capabilities")
async def bi_capabilities(
    user: RequireUser,
    industry: ActiveIndustry,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> dict[str, object]:
    return {
        "enabled": settings.ask_me_askbi_enabled and industry.value == "automotive",
        "engine": "askbi-v2",
        "schemaVersion": 2,
        "advancedEnabled": settings.ask_me_askbi_advanced_enabled,
        "maxQueries": 6,
        "migration": "0014_bi_reports",
    }


@router.get("/bi/region-options", response_model=FilterValuesResponse)
async def bi_region_options(service: AnalyticsServiceDep) -> FilterValuesResponse:
    _, scope = await bi_repository.context(service)
    values = await service.filter_values("region", limit=200)
    return _permitted_region_values(values, scope)


def _permitted_region_values(
    values: FilterValuesResponse, scope: RegionScope
) -> FilterValuesResponse:
    return values.model_copy(
        update={
            "values": [
                item
                for item in values.values
                if scope.unrestricted or zone_for_label(item.value) in scope.zones
            ]
        }
    )


@router.get("/bi/make-options", response_model=FilterValuesResponse)
async def bi_make_options(service: AnalyticsServiceDep) -> FilterValuesResponse:
    await bi_repository.context(service)
    # This connection applies the caller's region row policy. The shared value
    # dictionary is cached by industry and cannot provide scoped availability.
    rows = await service._analytics.execute(
        text(
            "SELECT DISTINCT c.make::text AS value "
            "FROM automotive.fact_sales AS s "
            "JOIN automotive.dim_carline AS c ON c.carline_id = s.carline_id "
            "WHERE c.make IS NOT NULL AND c.make::text <> '' "
            "ORDER BY value LIMIT 200"
        )
    )
    return FilterValuesResponse(
        domain="make",
        label="Make",
        values=[FilterValueItem(value=str(row.value)) for row in rows],
    )


@router.post("/bi/reports", response_model=BiReport, dependencies=[Depends(verify_csrf)])
async def bi_create(body: BiCreate, service: AnalyticsServiceDep) -> BiReport:
    return await bi_repository.create(service, body)


@router.get("/bi/reports", response_model=list[BiReport])
async def bi_reports(service: AnalyticsServiceDep) -> list[BiReport]:
    _, scope = await bi_repository.context(service)
    rows = (
        await service._app.scalars(
            select(BiReportRecord)
            .where(
                BiReportRecord.user_id == service._user.id,
                BiReportRecord.scope_key == bi_repository.scope_key(service, scope),
                BiReportRecord.saved.is_(True),
            )
            .limit(50)
        )
    ).all()
    return [bi_repository.view(row, service) for row in rows]


@router.get("/bi/reports/{report_id}", response_model=BiReport)
async def bi_get(report_id: uuid.UUID, service: AnalyticsServiceDep) -> BiReport:
    _, scope = await bi_repository.context(service)
    return bi_repository.view(await bi_repository.owned(service, report_id, scope), service)


@router.post(
    "/bi/reports/{report_id}/turns", response_model=BiReport, dependencies=[Depends(verify_csrf)]
)
async def bi_ask(
    report_id: uuid.UUID, body: BiTurnRequest, service: AnalyticsServiceDep
) -> BiReport:
    return await bi_turn(service, report_id, body)


@router.post(
    "/bi/reports/{report_id}/run",
    response_model=WorkspaceRunResponse,
    dependencies=[Depends(verify_csrf)],
)
async def bi_run(
    report_id: uuid.UUID, body: BiRunRequest, service: AnalyticsServiceDep
) -> WorkspaceRunResponse:
    return await bi_execution.run(service, report_id, body)


@router.post(
    "/bi/reports/{report_id}/narration",
    response_model=BiNarration,
    dependencies=[Depends(verify_csrf)],
)
async def bi_narrate(
    report_id: uuid.UUID, body: BiNarrationRequest, service: AnalyticsServiceDep
) -> BiNarration:
    return await bi_execution.narrate(service, report_id, body)


@router.post(
    "/workspace/plan", response_model=WorkspacePlanResponse, dependencies=[Depends(verify_csrf)]
)
async def workspace_plan(
    body: WorkspaceRequest, service: AnalyticsServiceDep
) -> WorkspacePlanResponse:
    return await plan_workspace(service, body)


@router.post(
    "/workspace/run", response_model=WorkspaceRunResponse, dependencies=[Depends(verify_csrf)]
)
async def workspace_run(
    body: WorkspaceRunRequest, service: AnalyticsServiceDep
) -> WorkspaceRunResponse:
    return await run_panel(service, body.panel)


@router.post(
    "/workspace/narration",
    response_model=WorkspaceNarrationResponse,
    dependencies=[Depends(verify_csrf)],
)
async def workspace_narration(
    body: WorkspaceNarrationRequest, service: AnalyticsServiceDep
) -> WorkspaceNarrationResponse:
    return await narrate_workspace(service, body)


@router.post("/workspaces", response_model=WorkspaceSaved, dependencies=[Depends(verify_csrf)])
async def workspace_save(
    body: WorkspaceSaveRequest, service: AnalyticsServiceDep
) -> WorkspaceSaved:
    return await save_workspace(service, body)


@router.get("/workspaces", response_model=list[WorkspaceSaved])
async def workspaces(service: AnalyticsServiceDep) -> list[WorkspaceSaved]:
    return await list_workspaces(service)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSaved)
async def workspace_get(workspace_id: uuid.UUID, service: AnalyticsServiceDep) -> WorkspaceSaved:
    return await get_workspace(service, workspace_id)


@router.get(
    "/capabilities",
    response_model=AnalyticsCapabilities,
    summary="Metrics, dimensions, analyses, filters and date ranges the builder supports",
)
async def capabilities(
    _user: RequireUser,
    industry: ActiveIndustry,
    registry: Annotated[DatabaseRegistry, Depends(get_registry)],
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> AnalyticsCapabilities:
    return await capabilities_for(semantic_service, industry, registry)


@router.post(
    "/inspect",
    response_model=AnalyticsInspection,
    summary="Validate a selection and return available options, fixes and suggestions",
)
async def inspect_analysis(
    body: AnalyticsInspectRequest,
    _user: RequireUser,
    industry: ActiveIndustry,
    semantic_service: Annotated[SemanticService, Depends(get_semantic_service)],
) -> AnalyticsInspection:
    return await inspect_spec(semantic_service, industry, body.spec)


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
