"""Entity Catalog request/response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel

ReadinessStatus = Literal["ai_ready", "needs_review", "missing_synonyms", "low_confidence"]


class CatalogRefreshInfo(ApiModel):
    id: str
    scope: str
    trigger: str
    status: str
    version: int
    load_id: str
    started_at: str | None = None
    finished_at: str | None = None
    rows_processed: int | None = None
    new_value_count: int = 0
    change_count: int = 0
    error: str | None = None


class SchemaDriftStatus(ApiModel):
    status: Literal["not_checked", "stable", "changes_detected", "action_required"]
    label: str
    count: int = 0


class CatalogSummary(ApiModel):
    industry: str
    last_refresh: CatalogRefreshInfo | None = None
    last_completed: CatalogRefreshInfo | None = None
    catalog_version: int = 0
    rows_processed: int | None = None
    last_load_id: str | None = None
    total_entities: int = 0
    total_values: int = 0
    new_values: int = 0
    schema_drift: SchemaDriftStatus
    ai_coverage: float | None = None
    entity_readiness: dict[str, int] = Field(default_factory=dict)


class EntityRow(ApiModel):
    key: str
    label: str
    group: str
    table: str
    column: str
    data_type: str | None = None
    distinct_values: int = 0
    new_values: int = 0
    last_updated: str | None = None
    ai_known: bool
    readiness: ReadinessStatus
    readiness_counts: dict[str, int] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)
    new_value_names: list[str] = Field(default_factory=list)
    error: str | None = None


class EntityValue(ApiModel):
    value: str
    frequency: int
    is_new: bool
    active: bool
    first_seen_at: str | None = None
    detected_in_load: str | None = None
    readiness: ReadinessStatus
    readiness_notes: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    resolution_rule: list[str] = Field(default_factory=list)


class EntityDetail(EntityRow):
    max_values: int
    values: list[EntityValue] = Field(default_factory=list)
    values_total: int = 0


class CatalogChangeItem(ApiModel):
    id: str
    kind: str
    severity: str
    summary: str
    table: str | None = None
    column: str | None = None
    domain_key: str | None = None
    confidence: float | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    impact: dict[str, str] = Field(default_factory=dict)
    detected_at: str | None = None


class CatalogRefreshRequest(ApiModel):
    scope: Literal["catalog", "values", "semantic_cache"] = "catalog"
    trigger: Literal["manual", "data_load"] = "manual"
    load_id: str | None = Field(default=None, max_length=80)


class CatalogRefreshResult(ApiModel):
    refresh: CatalogRefreshInfo
    summary: CatalogSummary
