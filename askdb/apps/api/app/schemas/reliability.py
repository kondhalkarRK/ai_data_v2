"""Data Reliability Center request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import ApiModel

DimensionKey = Literal[
    "accuracy", "completeness", "consistency", "timeliness", "validity", "uniqueness"
]
SeverityKey = Literal["critical", "high", "medium", "low"]
RuleStatusKey = Literal["passing", "failing", "no_data", "error", "disabled"]
Tone = Literal["positive", "info", "warning", "risk"]
MonitorKind = Literal[
    "not_null", "unique", "range", "allowed_values", "pattern", "freshness", "reference"
]
BulkAction = Literal[
    "assign_dimension",
    "assign_owner",
    "add_tags",
    "remove_tags",
    "set_severity",
    "enable",
    "disable",
]


class ReliabilityHero(ApiModel):
    available: bool
    unavailable_reason: str | None = None
    score: float | None = None
    band: str
    band_label: str
    delta_7d: float | None = None
    rules_total: int = 0
    rules_active: int = 0
    rules_passing: int = 0
    rules_failing: int = 0
    rules_errored: int = 0
    critical_issues: int = 0
    datasets_monitored: int = 0
    records_checked: int = 0


class SummaryStatement(ApiModel):
    tone: Tone
    text: str


class TrustSummary(ApiModel):
    headline: str
    statements: list[SummaryStatement] = Field(default_factory=list)


class DimensionCard(ApiModel):
    key: DimensionKey
    label: str
    question: str
    weight: float
    effective_weight: float | None = None
    score: float | None = None
    band: str
    rules: int = 0
    passing: int = 0
    failing: int = 0
    errored: int = 0
    delta_7d: float | None = None
    sparkline: list[float | None] = Field(default_factory=list)
    last_failure_at: str | None = None
    top_issue: str | None = None


class TrendPointOut(ApiModel):
    date: str
    score: float | None = None
    dimensions: dict[str, float | None] = Field(default_factory=dict)
    measured: float | None = None


class TrendEvent(ApiModel):
    date: str
    kind: Literal["drop", "incident", "drift"]
    title: str
    detail: str = ""
    rule_ids: list[str] = Field(default_factory=list)


class TrustTrend(ApiModel):
    points: list[TrendPointOut] = Field(default_factory=list)
    events: list[TrendEvent] = Field(default_factory=list)
    basis: str = ""
    measured_runs: int = 0
    end_date: str | None = None


class RuleRow(ApiModel):
    id: str
    name: str
    description: str
    dimension: DimensionKey
    dataset: str
    dataset_label: str
    severity: SeverityKey
    kind: str
    threshold: float
    unit: str
    status: RuleStatusKey
    pass_rate: float | None = None
    score: float | None = None
    total: int = 0
    failed: int = 0
    observed: str = ""
    value_at_risk: float | None = None
    last_run_at: str | None = None
    last_failure_at: str | None = None
    failing_since: str | None = None
    owner: str
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    custom: bool = False
    impact: str | None = None
    assets: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    sparkline: list[float] = Field(default_factory=list)
    duration_ms: int = 0


class AlertItem(ApiModel):
    id: str
    rule_id: str
    severity: SeverityKey
    kind: Literal["rule", "error"]
    title: str
    dataset: str
    dataset_label: str
    dimension: DimensionKey
    failed_records: int = 0
    unit: str = "records"
    impact: str
    value_at_risk: float | None = None
    detected_at: str | None = None
    assets: list[str] = Field(default_factory=list)


class ImpactItem(ApiModel):
    asset: str
    severity: SeverityKey
    statements: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class BusinessImpact(ApiModel):
    headline: str
    records_affected: int = 0
    value_at_risk: float | None = None
    items: list[ImpactItem] = Field(default_factory=list)


class DatasetTrust(ApiModel):
    name: str
    label: str
    kind: str
    domain: str
    score: float | None = None
    band: str
    rank: int | None = None
    rules: int = 0
    passing: int = 0
    failing: int = 0
    rows: int | None = None
    last_refresh: str | None = None
    top_issue: str | None = None
    assets: list[str] = Field(default_factory=list)


class FreshnessRow(ApiModel):
    dataset: str
    label: str
    cadence: str
    rule_id: str | None = None
    last_refresh: str | None = None
    expected_by: str | None = None
    sla_hours: float | None = None
    lag_hours: float | None = None
    delay_hours: float | None = None
    status: Literal["on_time", "delayed", "stale", "unknown"]


class DriftEvent(ApiModel):
    id: str
    kind: str
    severity: str
    summary: str
    table: str | None = None
    column: str | None = None
    detected_at: str | None = None
    impact: dict[str, str] = Field(default_factory=dict)


class SchemaDrift(ApiModel):
    status: Literal["stable", "drift", "not_checked", "unavailable"]
    label: str
    events: list[DriftEvent] = Field(default_factory=list)


class EntityValueOut(ApiModel):
    value: str
    domain: str
    first_seen_at: str | None = None


class EntityGroup(ApiModel):
    key: str
    label: str
    count: int
    values: list[EntityValueOut] = Field(default_factory=list)


class EntityChanges(ApiModel):
    available: bool
    total: int = 0
    last_refresh_at: str | None = None
    groups: list[EntityGroup] = Field(default_factory=list)


class MethodologyDimension(ApiModel):
    key: DimensionKey
    label: str
    weight: float
    effective_weight: float | None = None
    measured: bool


class TrustBand(ApiModel):
    key: str
    label: str
    min: float


class Methodology(ApiModel):
    formula: str
    dimensions: list[MethodologyDimension]
    severity_weights: dict[str, float]
    bands: list[TrustBand]
    notes: list[str] = Field(default_factory=list)


class InsightItem(ApiModel):
    id: str
    tone: Tone
    title: str
    detail: str
    rule_ids: list[str] = Field(default_factory=list)
    dimension: DimensionKey | None = None
    dataset: str | None = None


class CatalogColumn(ApiModel):
    name: str
    label: str
    type: str


class CatalogDataset(ApiModel):
    name: str
    label: str
    columns: list[CatalogColumn] = Field(default_factory=list)


class MonitorCatalog(ApiModel):
    datasets: list[CatalogDataset] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Capability(ApiModel):
    key: str
    label: str
    status: Literal["live", "next", "planned"]
    detail: str


class DataReliabilityResponse(ApiModel):
    industry: str
    computed_at: str
    data_as_of: str | None = None
    storage: Literal["database", "memory"]
    run_duration_ms: int = 0
    hero: ReliabilityHero
    summary: TrustSummary
    dimensions: list[DimensionCard]
    trend: TrustTrend
    rules: list[RuleRow]
    alerts: list[AlertItem]
    impact: BusinessImpact
    datasets: list[DatasetTrust]
    freshness: list[FreshnessRow]
    schema_drift: SchemaDrift
    entities: EntityChanges
    methodology: Methodology
    insights: list[InsightItem]
    catalog: MonitorCatalog
    capabilities: list[Capability]


def _clean_tags(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    tags = [v.strip().lower()[:40] for v in values if v and v.strip()]
    return list(dict.fromkeys(tags))[:12]


class CreateMonitorRequest(ApiModel):
    name: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=400)
    dimension: DimensionKey
    dataset: str = Field(min_length=1, max_length=120)
    severity: SeverityKey
    kind: MonitorKind
    column: str | None = Field(default=None, max_length=120)
    columns: list[str] | None = Field(default=None, max_length=8)
    min_value: float | None = None
    max_value: float | None = None
    allowed: list[str] | None = Field(default=None, max_length=200)
    pattern: str | None = Field(default=None, max_length=200)
    max_age_hours: float | None = Field(default=None, gt=0, le=24 * 400)
    ref_dataset: str | None = Field(default=None, max_length=120)
    ref_column: str | None = Field(default=None, max_length=120)
    threshold: float = Field(default=100, ge=0, le=100)
    owner: str = Field(default="Data Engineering", min_length=1, max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        return _clean_tags(value) or []


class UpdateMonitorRequest(ApiModel):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    dimension: DimensionKey | None = None
    severity: SeverityKey | None = None
    threshold: float | None = Field(default=None, ge=0, le=100)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=12)
    enabled: bool | None = None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_tags(value)


class BulkMonitorRequest(ApiModel):
    rule_ids: list[str] = Field(min_length=1, max_length=200)
    action: BulkAction
    value: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = Field(default=None, max_length=12)

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return _clean_tags(value)


class MonitorMutationResult(ApiModel):
    ok: bool
    updated: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    storage: Literal["database", "memory"]
    message: str | None = None
