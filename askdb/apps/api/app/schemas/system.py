"""Health, readiness, industry and diagnostics models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.core.config import Industry
from app.schemas.common import ApiModel

DependencyStatus = Literal["ok", "degraded", "unavailable", "not_configured"]


class HealthResponse(ApiModel):
    """Liveness. Answers only 'is this process running'."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    time: datetime


class DependencyReport(ApiModel):
    name: str
    status: DependencyStatus
    detail: str
    latency_ms: int | None = None


class ReadinessResponse(ApiModel):
    """Readiness. Answers 'can this process serve traffic'."""

    status: Literal["ready", "degraded", "not_ready"]
    checked_at: datetime
    dependencies: list[DependencyReport]


class IndustrySummary(ApiModel):
    id: Industry
    label: str
    description: str
    icon: str
    database_available: bool
    semantic_pack_loaded: bool
    is_default: bool


class IndustryListResponse(ApiModel):
    industries: list[IndustrySummary]
    active: Industry


class DiagnosticsResponse(ApiModel):
    """Protected diagnostics (spec section 18). Admin only, values redacted."""

    environment: str
    version: str
    uptime_seconds: int
    settings: dict[str, Any]
    dependencies: list[DependencyReport]
    caches: dict[str, Any]
