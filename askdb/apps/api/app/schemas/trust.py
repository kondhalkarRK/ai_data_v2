"""Data Trust Center response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel

Severity = Literal["critical", "high", "medium", "low", "info"]
IncidentStatus = Literal["open", "resolved", "recovering"]
PersonaView = Literal["overview", "technical"]


class TrustComponent(ApiModel):
    id: str
    label: str
    score: float
    weight: float
    contribution: float


class TrustScoreHero(ApiModel):
    score: float | None = None
    label: str
    available: bool = False
    unavailable_reason: str | None = None
    components: list[TrustComponent] = Field(default_factory=list)
    formula_note: str = ""
    datasets: int = 0
    dq_checks: int = 0
    active_incidents: int = 0
    schema_drift: int = 0


class BlastRadius(ApiModel):
    kpis: int = 0
    dashboards: int = 0
    insights: int = 0


class TrustIncident(ApiModel):
    id: str
    title: str
    summary: str
    severity: Severity
    status: IncidentStatus
    dataset: str
    detected_at: str
    resolved_at: str | None = None
    time_to_detect_hours: float | None = None
    time_to_resolve_hours: float | None = None
    impacted_assets: list[str] = Field(default_factory=list)
    root_cause_hint: str | None = None
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)


class TrendPoint(ApiModel):
    period: str
    trust_score: float | None = None
    failed_checks: int = 0
    freshness: float | None = None
    completeness: float | None = None
    schema_stability: float | None = None


class DatasetHealthCard(ApiModel):
    name: str
    display_name: str
    physical_name: str
    table_type: str
    health_score: float
    dimensions: dict[str, float]
    flags: dict[str, Literal["ok", "warn", "fail"]]
    sparkline: list[float] = Field(default_factory=list)
    last_refresh: str | None = None
    sla_hours: float | None = None
    classification: str = "Internal"
    certified: bool = False
    restricted: bool = False


class SchemaChange(ApiModel):
    dataset: str
    display_name: str
    from_version: int | None = None
    to_version: int | None = None
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    type_changes: list[dict[str, str]] = Field(default_factory=list)
    timeline: list[dict[str, str]] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
    detected_at: str | None = None


class ColumnProfile(ApiModel):
    name: str
    null_pct: float = 0
    distinct_count: int | None = None
    min_value: str | None = None
    max_value: str | None = None
    top_values: list[dict[str, Any]] = Field(default_factory=list)
    pattern: str | None = None
    issue: str | None = None


class DatasetProfile(ApiModel):
    name: str
    display_name: str
    rows: int
    columns: int
    null_pct: float
    duplicates: float
    last_refresh: str | None = None
    column_profiles: list[ColumnProfile] = Field(default_factory=list)
    available: bool = True
    unavailable_reason: str | None = None


class GovernanceRecord(ApiModel):
    dataset: str
    display_name: str
    technical_owner: str | None = None
    business_owner: str | None = None
    classification: str = "Internal"
    certified: bool = False
    last_updated: str | None = None
    glossary_linked: bool = False
    semantic_linked: bool = True
    lineage_available: bool = True
    active_rules: int = 0
    restricted: bool = False
    visible: bool = True


class LineageImpact(ApiModel):
    dataset: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)
    explore_path: str = "/semantic/ontology"


class DqRule(ApiModel):
    id: str
    name: str
    dataset: str
    dimension: str
    threshold: float
    unit: str
    passing: bool
    observed: float
    owner: str
    last_modified: str
    editable: bool = False


class NotificationRule(ApiModel):
    id: str
    name: str
    min_severity: Severity
    channel: Literal["webhook", "email", "slack", "teams"]
    target: str = ""
    enabled: bool = False
    note: str | None = None


class AiStewardSection(ApiModel):
    summary: str
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    impact_assessment: str
    grounded_on: list[str] = Field(default_factory=list)


class DataTrustCenterResponse(ApiModel):
    industry: str
    computed_at: str
    data_as_of: str | None = None
    cache_ttl_seconds: int = 300
    hero: TrustScoreHero
    incidents: list[TrustIncident]
    incident_history: list[TrustIncident] = Field(default_factory=list)
    trends: list[TrendPoint]
    datasets: list[DatasetHealthCard]
    schema_changes: list[SchemaChange]
    profiles: list[DatasetProfile]
    governance: list[GovernanceRecord]
    lineage: list[LineageImpact]
    rules: list[DqRule]
    notification_rules: list[NotificationRule]
    steward: AiStewardSection
    default_view: PersonaView = "overview"


class UpdateRuleThresholdRequest(ApiModel):
    threshold: float


class StewardFeedbackRequest(ApiModel):
    vote: Literal["up", "down"]
    grounded_on: list[str] = Field(default_factory=list)
    body_preview: str | None = None
