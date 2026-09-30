"""Entity Catalog routes: summary, entities, changes and refresh."""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ActiveIndustry,
    RequireAnalyst,
    RequireViewer,
    get_app_session,
    get_registry,
    get_semantic_service,
)
from app.core.config import Industry
from app.core.exceptions import DependencyUnavailableError
from app.db.session import DatabaseRegistry
from app.models.catalog import CatalogChange
from app.schemas.catalog import (
    CatalogChangeItem,
    CatalogRefreshInfo,
    CatalogRefreshRequest,
    CatalogRefreshResult,
    CatalogSummary,
    EntityDetail,
    EntityRow,
    EntityValue,
    SchemaDriftStatus,
)
from app.semantic.service import SemanticService
from app.services.catalog import CatalogBusyError, EntityCatalogService
from app.services.catalog.config import build_catalog_config
from app.services.catalog.service import EntityView, refresh_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SessionDep = Annotated[AsyncSession, Depends(get_app_session)]
SemanticDep = Annotated[SemanticService, Depends(get_semantic_service)]
RegistryDep = Annotated[DatabaseRegistry, Depends(get_registry)]

_DETAIL_VALUE_LIMIT = 1000


def _row(view: EntityView) -> dict[str, object]:
    active = [v for v in view.values if v.active]
    aliases = list(dict.fromkeys(a for v in active for a in v.aliases))
    return {
        "key": view.domain.key,
        "label": view.domain.label,
        "group": view.domain.group,
        "table": view.domain.table,
        "column": view.domain.column,
        "data_type": view.data_type,
        "distinct_values": view.distinct,
        "new_values": len(view.new_values),
        "last_updated": view.last_updated.isoformat() if view.last_updated else None,
        "ai_known": view.domain.ai_known,
        "readiness": view.status,
        "readiness_counts": view.readiness_counts,
        "aliases": aliases[:40],
        "sample_values": [v.value for v in active[:25]],
        "new_value_names": [v.value for v in view.new_values[:25]],
        "error": view.error,
    }


def _change(item: CatalogChange) -> CatalogChangeItem:
    return CatalogChangeItem(
        id=str(item.id),
        kind=item.kind,
        severity=item.severity,
        summary=item.summary,
        table=item.table_name,
        column=item.column_name,
        domain_key=item.domain_key,
        confidence=item.confidence,
        detail=item.detail or {},
        impact={str(k): str(v) for k, v in (item.impact or {}).items()},
        detected_at=item.detected_at.isoformat() if item.detected_at else None,
    )


def _store_problem(exc: BaseException) -> str | None:
    """Why the catalog store cannot be used, or None for an unrelated error."""
    text = str(exc).lower()
    if isinstance(exc, ProgrammingError) or "does not exist" in text or "no such table" in text:
        return "migration_pending"
    if isinstance(exc, DBAPIError | DependencyUnavailableError | OSError):
        return "database_unreachable"
    return None


async def _reset(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:
        logger.debug("catalog: rollback after store failure failed", exc_info=True)


async def _pack_only_rows(semantic: SemanticService, industry: Industry) -> list[EntityRow]:
    """Entities straight from the semantic pack, used while the catalog store is down."""
    config = build_catalog_config(industry, await semantic.get_pack(industry))
    return [
        EntityRow(
            key=domain.key,
            label=domain.label,
            group=domain.group,
            table=domain.table,
            column=domain.column,
            ai_known=domain.ai_known,
            readiness="not_refreshed",
            aliases=list(dict.fromkeys(a for _, aliases in domain.value_aliases for a in aliases))[
                :40
            ],
            sample_values=[value for value, _ in domain.value_aliases][:25],
        )
        for domain in config.domains
    ]


@router.get("/summary", response_model=CatalogSummary)
async def catalog_summary(
    user: RequireViewer,
    industry: ActiveIndustry,
    session: SessionDep,
    semantic: SemanticDep,
) -> CatalogSummary:
    del user
    service = EntityCatalogService(session, semantic, industry)
    try:
        return CatalogSummary.model_validate(await service.summary())
    except Exception as exc:
        reason = _store_problem(exc)
        if reason is None:
            raise
        logger.warning("catalog summary unavailable (%s)", reason, exc_info=True)
        await _reset(session)
        rows = await _pack_only_rows(semantic, industry)
        return CatalogSummary(
            industry=industry.value,
            total_entities=len(rows),
            schema_drift=SchemaDriftStatus(status="not_checked", label="Not checked yet"),
            available=False,
            unavailable_reason=reason,
        )


@router.get("/entities", response_model=list[EntityRow])
async def catalog_entities(
    user: RequireViewer,
    industry: ActiveIndustry,
    session: SessionDep,
    semantic: SemanticDep,
) -> list[EntityRow]:
    del user
    service = EntityCatalogService(session, semantic, industry)
    try:
        return [EntityRow.model_validate(_row(view)) for view in await service.entity_views()]
    except Exception as exc:
        if _store_problem(exc) is None:
            raise
        await _reset(session)
        return await _pack_only_rows(semantic, industry)


@router.get("/entities/{key}", response_model=EntityDetail)
async def catalog_entity(
    key: str,
    user: RequireViewer,
    industry: ActiveIndustry,
    session: SessionDep,
    semantic: SemanticDep,
) -> EntityDetail:
    del user
    service = EntityCatalogService(session, semantic, industry)
    try:
        views = await service.entity_views(domain_key=key)
    except Exception as exc:
        if _store_problem(exc) is None:
            raise
        await _reset(session)
        row = next((r for r in await _pack_only_rows(semantic, industry) if r.key == key), None)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown catalog entity.") from exc
        domain = build_catalog_config(industry, await semantic.get_pack(industry)).domain(key)
        return EntityDetail(**row.model_dump(), max_values=domain.max_values if domain else 0)
    if not views:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown catalog entity.")
    view = views[0]
    ordered = sorted(view.values, key=lambda v: (not v.is_new, not v.active, -v.frequency))
    values = [
        EntityValue(
            value=v.value,
            frequency=v.frequency,
            is_new=v.is_new,
            active=v.active,
            first_seen_at=v.first_seen_at.isoformat() if v.first_seen_at else None,
            detected_in_load=v.first_seen_load,
            readiness=v.readiness.status,
            readiness_notes=v.readiness.notes,
            aliases=v.aliases,
            resolution_rule=v.readiness.rule,
        )
        for v in ordered[:_DETAIL_VALUE_LIMIT]
    ]
    return EntityDetail.model_validate(
        {
            **_row(view),
            "max_values": view.domain.max_values,
            "values": values,
            "values_total": len(view.values),
        }
    )


@router.get("/changes", response_model=list[CatalogChangeItem])
async def catalog_changes(
    user: RequireViewer,
    industry: ActiveIndustry,
    session: SessionDep,
    semantic: SemanticDep,
    limit: int = Query(default=200, ge=1, le=500),
) -> list[CatalogChangeItem]:
    del user
    service = EntityCatalogService(session, semantic, industry)
    try:
        return [_change(item) for item in await service.changes(limit=limit)]
    except Exception as exc:
        if _store_problem(exc) is None:
            raise
        await _reset(session)
        return []


@router.post("/refresh", response_model=CatalogRefreshResult)
async def catalog_refresh(
    body: CatalogRefreshRequest,
    user: RequireAnalyst,
    industry: ActiveIndustry,
    session: SessionDep,
    semantic: SemanticDep,
    registry: RegistryDep,
) -> CatalogRefreshResult:
    """Manual refresh, or the data-load completion hook (``trigger: data_load``)."""
    async with AsyncExitStack() as stack:
        analytics = None
        if body.scope != "semantic_cache":
            try:
                analytics = await stack.enter_async_context(registry.analytics_connection(industry))
            except Exception:
                logger.warning("catalog refresh: warehouse unavailable", exc_info=True)
        service = EntityCatalogService(session, semantic, industry, analytics=analytics)
        try:
            run = await service.refresh(
                scope=body.scope,
                trigger=body.trigger,
                load_id=body.load_id,
                requested_by=user.email,
            )
        except CatalogBusyError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "A catalog refresh is already running."
            ) from exc
        except Exception as exc:
            reason = _store_problem(exc)
            if reason is None:
                raise
            await _reset(session)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The catalog store is not set up yet (run the database migration)."
                if reason == "migration_pending"
                else "The application database is not reachable.",
            ) from exc
        info = refresh_dict(run)
        assert info is not None
        return CatalogRefreshResult(
            refresh=CatalogRefreshInfo.model_validate(info),
            summary=CatalogSummary.model_validate(await service.summary()),
        )
