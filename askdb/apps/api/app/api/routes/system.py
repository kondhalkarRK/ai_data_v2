"""Health, readiness, industries and protected diagnostics."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    CurrentUser,
    RequireAdmin,
    get_app_settings,
    get_registry,
    get_semantic_service,
)
from app.core.config import Industry, Settings
from app.core.exceptions import NqlError
from app.db.session import DatabaseRegistry
from app.schemas.system import (
    DependencyReport,
    DiagnosticsResponse,
    HealthResponse,
    IndustryListResponse,
    IndustrySummary,
    ReadinessResponse,
)
from app.semantic.service import SemanticService

router = APIRouter()

SERVICE_NAME = "nql-insight-api"
SERVICE_VERSION = "0.1.0"
_STARTED_AT = time.monotonic()

RegistryDep = Annotated[DatabaseRegistry, Depends(get_registry)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SemanticServiceDep = Annotated[SemanticService, Depends(get_semantic_service)]

INDUSTRY_METADATA: dict[Industry, dict[str, str]] = {
    Industry.AUTOMOTIVE: {
        "label": "Automotive",
        "icon": "car",
        "description": "Vehicle sales, inventory, warranty claims and dealer performance.",
    },
    Industry.INSURANCE: {
        "label": "Insurance",
        "icon": "shield",
        "description": "Policy premium, claims, loss ratio and renewal analytics.",
    },
}


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Liveness probe",
)
async def health(settings: SettingsDep) -> HealthResponse:
    """Unauthenticated. Reports only that the process is up, never dependency detail."""
    return HealthResponse(
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        environment=settings.environment.value,
        time=datetime.now(UTC),
    )


async def _dependency_reports(
    registry: DatabaseRegistry, settings: Settings
) -> list[DependencyReport]:
    reports: list[DependencyReport] = []

    started = time.perf_counter()
    ok, detail = await registry.check_app_database()
    reports.append(
        DependencyReport(
            name="postgres:app",
            status="ok" if ok else "unavailable",
            detail=detail,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    )

    for industry in Industry:
        started = time.perf_counter()
        ok, detail = await registry.check_analytics_database(industry)
        reports.append(
            DependencyReport(
                name=f"postgres:{industry.value}",
                status="ok" if ok else "unavailable",
                detail=detail,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    # Reported as not_configured until Phase 6 wires them up, so readiness is honest
    # about what is and is not available rather than silently claiming success.
    reports.append(
        DependencyReport(
            name="mongodb",
            status="not_configured" if not settings.mongodb_uri else "ok",
            detail="RAG document store (activated in Phase 6).",
        )
    )
    reports.append(
        DependencyReport(
            name="qdrant",
            status="not_configured" if not settings.qdrant_url else "ok",
            detail="Vector store (activated in Phase 6).",
        )
    )
    reports.append(
        DependencyReport(
            name="llm",
            status="ok" if settings.llm_api_key.get_secret_value() else "not_configured",
            detail=f"model={settings.llm_default_model}",
        )
    )
    return reports


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["system"],
    summary="Readiness probe",
)
async def ready(
    response: Response, registry: RegistryDep, settings: SettingsDep
) -> ReadinessResponse:
    """Unauthenticated but detail-light.

    The application database is required. An analytics database being down degrades the
    service rather than taking it offline, because the other industry may still work.
    """
    reports = await _dependency_reports(registry, settings)
    by_name = {report.name: report for report in reports}

    app_ok = by_name["postgres:app"].status == "ok"
    analytics_ok = any(
        by_name[f"postgres:{industry.value}"].status == "ok" for industry in Industry
    )

    if not app_ok:
        overall = "not_ready"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif not analytics_ok or any(report.status == "unavailable" for report in reports):
        overall = "degraded"
    else:
        overall = "ready"

    return ReadinessResponse(status=overall, checked_at=datetime.now(UTC), dependencies=reports)


@router.get(
    "/api/v1/industries",
    response_model=IndustryListResponse,
    tags=["system"],
    summary="Available industry packs",
)
async def list_industries(
    user: CurrentUser, registry: RegistryDep, semantic: SemanticServiceDep
) -> IndustryListResponse:
    summaries: list[IndustrySummary] = []
    for industry in Industry:
        available, _ = await registry.check_analytics_database(industry)
        semantic_pack_loaded = True
        try:
            await semantic.get_summary(industry)
        except NqlError:
            semantic_pack_loaded = False
        meta = INDUSTRY_METADATA[industry]
        summaries.append(
            IndustrySummary(
                id=industry,
                label=meta["label"],
                description=meta["description"],
                icon=meta["icon"],
                database_available=available,
                semantic_pack_loaded=semantic_pack_loaded,
                is_default=industry is user.default_industry,
            )
        )
    return IndustryListResponse(industries=summaries, active=user.default_industry)


@router.get(
    "/api/v1/diagnostics",
    response_model=DiagnosticsResponse,
    tags=["system"],
    summary="Protected diagnostics (admin only)",
)
async def diagnostics(
    admin: RequireAdmin,
    registry: RegistryDep,
    settings: SettingsDep,
    semantic: SemanticServiceDep,
) -> DiagnosticsResponse:
    """Operational detail for administrators.

    Only non-secret configuration is echoed. Secrets are reported as a boolean
    'configured' flag rather than a redacted value, so there is nothing to leak.
    """
    safe_settings = {
        "log_level": settings.log_level,
        "default_industry": settings.default_industry.value,
        "sql_max_result_rows": settings.sql_max_result_rows,
        "sql_statement_timeout_seconds": settings.sql_statement_timeout_seconds,
        "db_pool_max_size": settings.db_pool_max_size,
        "jwt_access_ttl_minutes": settings.jwt_access_ttl_minutes,
        "jwt_refresh_ttl_days": settings.jwt_refresh_ttl_days,
        "cookie_secure": settings.cookie_secure,
        "cookie_samesite": settings.cookie_samesite,
        "cors_allowed_origins": settings.cors_allowed_origins,
        "rate_limit_login_per_minute": settings.rate_limit_login_per_minute,
        "embeddings_provider": settings.embeddings_provider,
        "llm_default_model": settings.llm_default_model,
        "web_retrieval_enabled": settings.web_retrieval_enabled,
        "secrets_configured": {
            "jwt_secret_key": bool(settings.jwt_secret_key.get_secret_value()),
            "llm_api_key": bool(settings.llm_api_key.get_secret_value()),
            "qdrant_api_key": bool(settings.qdrant_api_key.get_secret_value()),
        },
    }

    return DiagnosticsResponse(
        environment=settings.environment.value,
        version=SERVICE_VERSION,
        uptime_seconds=int(time.monotonic() - _STARTED_AT),
        settings=safe_settings,
        dependencies=await _dependency_reports(registry, settings),
        caches=semantic.cache_stats,
    )
