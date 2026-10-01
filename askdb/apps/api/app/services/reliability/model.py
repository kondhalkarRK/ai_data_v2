"""Data Reliability Center domain model: dimensions, rules, datasets and run results."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any, Literal

Dimension = Literal[
    "accuracy", "completeness", "consistency", "timeliness", "validity", "uniqueness"
]
Severity = Literal["critical", "high", "medium", "low"]
RuleKind = Literal[
    "row_check",
    "not_null",
    "unique",
    "reference",
    "range",
    "allowed_values",
    "pattern",
    "freshness",
    "metric",
]
RuleStatus = Literal["passing", "failing", "no_data", "error", "disabled"]

DIMENSIONS: tuple[Dimension, ...] = (
    "accuracy",
    "completeness",
    "consistency",
    "timeliness",
    "validity",
    "uniqueness",
)
SEVERITIES: tuple[Severity, ...] = ("critical", "high", "medium", "low")


@dataclass(frozen=True, slots=True)
class DimensionInfo:
    key: Dimension
    label: str
    weight: float
    question: str


DIMENSION_INFO: dict[Dimension, DimensionInfo] = {
    "accuracy": DimensionInfo(
        "accuracy", "Accuracy", 25, "Do the numbers reconcile with business reality?"
    ),
    "completeness": DimensionInfo(
        "completeness", "Completeness", 20, "Is every expected record and attribute present?"
    ),
    "consistency": DimensionInfo(
        "consistency", "Consistency", 15, "Do related datasets agree with each other?"
    ),
    "timeliness": DimensionInfo(
        "timeliness", "Timeliness", 15, "Is the data refreshed within its agreed SLA?"
    ),
    "validity": DimensionInfo(
        "validity", "Validity", 15, "Do values follow the business formats and ranges?"
    ),
    "uniqueness": DimensionInfo(
        "uniqueness", "Uniqueness", 10, "Is every business entity recorded exactly once?"
    ),
}

SEVERITY_WEIGHT: dict[Severity, float] = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Trust bands shown on the gauge (lower bound inclusive).
TRUST_BANDS: tuple[tuple[float, str, str], ...] = (
    (95, "excellent", "Excellent"),
    (85, "good", "Good"),
    (70, "fair", "Fair"),
    (0, "risk", "Risk"),
)


def band_for(score: float | None) -> tuple[str, str]:
    if score is None:
        return "unknown", "Not measured"
    for floor, key, label in TRUST_BANDS:
        if score >= floor:
            return key, label
    return "risk", "Risk"


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """A monitored dataset. ``name`` matches the semantic table name where one exists."""

    name: str
    physical: str
    display_name: str
    kind: Literal["fact", "dimension", "aggregate", "plan"]
    domain: str
    key_column: str | None = None
    date_column: str | None = None
    cadence: Literal["daily", "monthly", "static"] = "static"
    sla_hours: float | None = None
    value_column: str | None = None
    assets: tuple[str, ...] = ()
    # Columns custom monitors may reference when the dataset is not in the semantic pack.
    columns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """One data-quality rule.

    Population rules report ``total`` units checked and ``failed`` units; the pass rate is
    ``1 - failed / total``. ``threshold`` is the minimum pass rate (percent) for the rule to
    pass. Freshness rules use ``max_age_hours`` instead.
    """

    id: str
    name: str
    dimension: Dimension
    dataset: str
    severity: Severity
    kind: RuleKind
    description: str
    owner: str
    threshold: float = 100.0
    tags: tuple[str, ...] = ()
    impact: str = ""
    assets: tuple[str, ...] = ()
    unit: str = "records"
    enabled: bool = True
    custom: bool = False
    # row_check: SQL predicate that is TRUE for a valid row (alias ``t``); NULL counts as invalid.
    condition: str | None = None
    column: str | None = None
    columns: tuple[str, ...] = ()
    ref_dataset: str | None = None
    ref_column: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    allowed: tuple[str, ...] = ()
    pattern: str | None = None
    max_age_hours: float | None = None
    # Built-in rules only: SQL predicate restricting the population (alias ``t``).
    scope: str | None = None
    # metric: SQL returning one row (total, failed[, value_at_risk]).
    sql: str | None = None
    # Optional SQL returning up to five text examples of failing units.
    sample_sql: str | None = None
    # Optional SQL returning (period date, total, failed) rows for the record-date trend.
    trend_sql: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def with_overrides(self, overrides: dict[str, Any]) -> RuleSpec:
        allowed = {"name", "dimension", "severity", "threshold", "owner", "tags", "enabled"}
        changes = {k: v for k, v in overrides.items() if k in allowed and v is not None}
        if "tags" in changes:
            changes["tags"] = tuple(changes["tags"])
        return replace(self, **changes) if changes else self


@dataclass(slots=True)
class RuleResult:
    rule_id: str
    status: RuleStatus
    total: int = 0
    failed: int = 0
    pass_rate: float | None = None
    score: float | None = None
    observed: str = ""
    value_at_risk: float | None = None
    samples: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    lag_hours: float | None = None
    last_value: date | datetime | None = None
    trend: dict[date, tuple[int, int]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "passing"


@dataclass(slots=True)
class RunHistory:
    """What the store knows about earlier runs of one rule."""

    last_failure_at: datetime | None = None
    failing_since: datetime | None = None
    recent_pass_rates: list[float] = field(default_factory=list)
    runs: int = 0
