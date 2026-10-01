"""Admin Center: AI governance, usage dashboards, DQ / semantic refreshes and the audit log."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAdmin,
    get_app_session,
    get_app_settings,
    get_registry,
    get_semantic_service,
    verify_csrf,
)
from app.api.routes.catalog import catalog_refresh
from app.core.config import Settings
from app.db.session import DatabaseRegistry
from app.schemas.catalog import CatalogRefreshRequest
from app.schemas.common import ApiModel
from app.schemas.reliability import UpdateMonitorRequest
from app.semantic.service import SemanticService
from app.services.chat.query_cache import QUERY_CACHE
from app.services.chat.value_dictionary import invalidate_value_dictionary
from app.services.governance import (
    AdminAction,
    active_llm,
    audit_counts,
    audit_log,
    governance_overview,
    llm_usage_overview,
    provider_options,
    record_admin_action,
    sync_llm_config,
    update_llm_config,
)
from app.services.governance.audit import AUDIT_CATEGORIES
from app.services.reliability import (
    DataReliabilityService,
    clear_reliability_cache,
    shared_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_csrf)])

SessionDep = Annotated[AsyncSession, Depends(get_app_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SemanticDep = Annotated[SemanticService, Depends(get_semantic_service)]
RegistryDep = Annotated[DatabaseRegistry, Depends(get_registry)]


class UpdateLlmRequest(ApiModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)
    temperature: float = Field(ge=0.0, le=1.5)
    max_tokens: int = Field(ge=64, le=8000)


class ToggleRuleRequest(ApiModel):
    enabled: bool


def _done(action: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "action": action, "message": message, **extra}


# --- AI governance -------------------------------------------------------------


@router.get("/llm")
async def get_llm(
    admin: RequireAdmin, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    del admin
    current = await sync_llm_config(session, settings)
    return {"current": current.to_dict(), "providers": provider_options(settings)}


@router.put("/llm")
async def put_llm(
    body: UpdateLlmRequest, admin: RequireAdmin, session: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    current = await update_llm_config(
        session,
        settings,
        admin,
        provider=body.provider,
        model=body.model,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )
    return {"current": current.to_dict(), "providers": provider_options(settings)}


# --- dashboards ----------------------------------------------------------------


@router.get("/governance")
async def governance(
    admin: RequireAdmin,
    session: SessionDep,
    settings: SettingsDep,
    days: int = Query(default=30, ge=1, le=90),
) -> dict[str, Any]:
    del admin
    overview = await governance_overview(session, days=days)
    return {**overview, "llm": active_llm(settings).to_dict()}


@router.get("/usage")
async def usage(
    admin: RequireAdmin, session: SessionDep, days: int = Query(default=30, ge=1, le=90)
) -> dict[str, Any]:
    del admin
    return await llm_usage_overview(session, days=days)


@router.get("/audit")
async def audit(
    admin: RequireAdmin,
    session: SessionDep,
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    del admin
    if category is not None and category not in AUDIT_CATEGORIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown audit category.")
    return {
        "items": await audit_log(session, category=category, limit=limit),
        "counts": await audit_counts(session),
        "categories": list(AUDIT_CATEGORIES),
    }


# --- Data Trust administration -----------------------------------------------


@router.get("/dq/rules")
async def dq_rules(
    admin: RequireAdmin, industry: ActiveIndustry, semantic: SemanticDep, session: SessionDep
) -> list[dict[str, Any]]:
    del admin
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "dimension": str(rule.dimension),
            "dataset": rule.dataset,
            "severity": str(rule.severity),
            "enabled": rule.enabled,
            "custom": rule.custom,
        }
        for rule in await service.rules()
    ]


@router.post("/dq/refresh-rules")
async def dq_refresh_rules(
    admin: RequireAdmin, industry: ActiveIndustry, semantic: SemanticDep, session: SessionDep
) -> dict[str, Any]:
    clear_reliability_cache(industry.value)
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    count = len(await service.rules())
    await record_admin_action(
        session, admin.id, AdminAction.REFRESHED_DQ_RULES, f"{count} rules ({industry.value})"
    )
    return _done("dq_rules", f"Reloaded {count} data-quality rules.", count=count)


@router.post("/dq/refresh-scores")
async def dq_refresh_scores(
    admin: RequireAdmin,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
    registry: RegistryDep,
) -> dict[str, Any]:
    async with registry.analytics_connection(industry) as connection:
        service = DataReliabilityService(
            connection=connection, semantic=semantic, industry=industry, app_session=session
        )
        await service.center(refresh=True, user=admin.email)
    snapshot = shared_snapshot(industry.value) or {}
    score = snapshot.get("score")
    await record_admin_action(
        session,
        admin.id,
        AdminAction.REFRESHED_TRUST_SCORES,
        f"Score: {score if score is not None else 'not measured'} ({industry.value})",
    )
    message = (
        f"Trust score recalculated: {score}." if score is not None else "Trust scores recalculated."
    )
    return _done("trust_scores", message, score=score)


@router.post("/dq/rules/{rule_id}/toggle")
async def dq_toggle_rule(
    rule_id: str,
    body: ToggleRuleRequest,
    admin: RequireAdmin,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
) -> dict[str, Any]:
    service = DataReliabilityService(
        connection=None, semantic=semantic, industry=industry, app_session=session
    )
    result = await service.update_monitor(
        rule_id, UpdateMonitorRequest(enabled=body.enabled), admin.email
    )
    if not result.ok and rule_id in result.skipped:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found.")
    await record_admin_action(
        session,
        admin.id,
        AdminAction.ENABLED_DQ_RULE if body.enabled else AdminAction.DISABLED_DQ_RULE,
        f"Rule: {rule_id} ({industry.value})",
    )
    state = "enabled" if body.enabled else "disabled"
    return _done("dq_rule", f"Rule {rule_id} {state}.", ruleId=rule_id, enabled=body.enabled)


# --- Semantic administration -------------------------------------------------


@router.post("/semantic/{target}")
async def semantic_refresh(
    target: Literal["catalog", "metadata", "graph", "cache"],
    admin: RequireAdmin,
    industry: ActiveIndustry,
    semantic: SemanticDep,
    session: SessionDep,
    registry: RegistryDep,
) -> dict[str, Any]:
    if target == "catalog":
        result = await catalog_refresh(
            body=CatalogRefreshRequest(scope="catalog"),
            user=admin,
            industry=industry,
            session=session,
            semantic=semantic,
            registry=registry,
        )
        return _done("catalog", "Entity catalog refreshed.", status=result.refresh.status)

    if target == "metadata":
        semantic.invalidate(industry)
        invalidate_value_dictionary(industry)
        summary = (await semantic.get_pack(industry)).summary
        await record_admin_action(
            session,
            admin.id,
            AdminAction.REFRESHED_SEMANTIC_METADATA,
            f"{summary.table_count} tables, {summary.measure_count} measures ({industry.value})",
        )
        return _done(
            "metadata",
            f"Semantic metadata reloaded: {summary.table_count} tables, "
            f"{summary.measure_count} measures.",
        )

    if target == "graph":
        semantic.invalidate_graph(industry)
        snapshot = await semantic.get_snapshot(industry)
        await record_admin_action(
            session,
            admin.id,
            AdminAction.REFRESHED_KNOWLEDGE_GRAPH,
            f"{len(snapshot.nodes)} nodes, {len(snapshot.edges)} edges ({industry.value})",
        )
        return _done(
            "graph",
            f"Knowledge graph rebuilt: {len(snapshot.nodes)} nodes, {len(snapshot.edges)} edges.",
        )

    cleared = QUERY_CACHE.stats().get("entries", 0)
    QUERY_CACHE.clear()
    await catalog_refresh(
        body=CatalogRefreshRequest(scope="semantic_cache"),
        user=admin,
        industry=industry,
        session=session,
        semantic=semantic,
        registry=registry,
    )
    return _done("cache", "Semantic cache cleared.", cleared=cleared)
