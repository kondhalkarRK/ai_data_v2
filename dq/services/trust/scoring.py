"""Derive dimension scores and incidents from live DQ reports — no invented metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from app.services.trust.config import trust_weights

Severity = Literal["critical", "high", "medium", "low", "info"]
Status = Literal["open", "resolved", "recovering"]


def dimension_scores(report: dict[str, Any], *, freshness_hours: float | None, sla_hours: float | None) -> dict[str, float]:
    """Map existing DQ engine outputs into Trust Score dimensions (0–100)."""
    completeness = max(0.0, 100.0 - float(report.get("total_null_pct") or 0) * 1.5)
    uniqueness = max(0.0, 100.0 - float(report.get("duplicate_pct") or 0) * 2.0)
    validity = max(
        0.0,
        100.0
        - min(len(report.get("type_issues") or []) * 8, 40)
        - min(len(report.get("outliers") or {}) * 4, 20),
    )
    consistency = max(
        0.0,
        100.0
        - min(len(report.get("cardinality_flags") or []) * 5, 30)
        - min(len(report.get("date_gaps") or []) * 4, 20),
    )
    # Schema stability: no historical diff → treat type issues as proxy; 100 if clean.
    schema_stability = max(0.0, 100.0 - min(len(report.get("type_issues") or []) * 10, 50))
    # Rule success: each finding type is a soft check.
    checks_total = 5
    failed = 0
    if float(report.get("total_null_pct") or 0) >= 5:
        failed += 1
    if float(report.get("duplicate_pct") or 0) >= 1:
        failed += 1
    if report.get("type_issues"):
        failed += 1
    if report.get("date_gaps"):
        failed += 1
    if report.get("outliers"):
        failed += 1
    dq_rule_success = ((checks_total - failed) / checks_total) * 100.0

    if freshness_hours is None or sla_hours is None:
        freshness = 70.0  # Unknown freshness — never pretend it's perfect.
    elif freshness_hours <= sla_hours:
        freshness = 100.0
    else:
        over = freshness_hours - sla_hours
        freshness = max(0.0, 100.0 - (over / max(sla_hours, 1)) * 40)

    return {
        "freshness": round(freshness, 1),
        "completeness": round(completeness, 1),
        "uniqueness": round(uniqueness, 1),
        "validity": round(validity, 1),
        "consistency": round(consistency, 1),
        "schema_stability": round(schema_stability, 1),
        "dq_rule_success": round(dq_rule_success, 1),
    }


def aggregate_trust_score(dimension_avgs: dict[str, float]) -> tuple[float | None, list[dict[str, Any]]]:
    weights = trust_weights()
    usable = 0.0
    acc = 0.0
    components: list[dict[str, Any]] = []
    for key, weight in weights.items():
        value = dimension_avgs.get(key)
        if value is None:
            continue
        usable += weight
        acc += value * weight
        components.append(
            {
                "id": key,
                "label": key.replace("_", " ").title(),
                "score": value,
                "weight": weight,
                "contribution": round(value * weight, 2),
            }
        )
    if usable <= 0:
        return None, components
    return round(acc / usable, 1), components


def label_for_score(score: float | None) -> str:
    if score is None:
        return "Unavailable"
    if score >= 90:
        return "Healthy"
    if score >= 75:
        return "Watch"
    if score >= 50:
        return "At risk"
    return "Critical"


def build_incidents_for_table(
    *,
    table_name: str,
    display_name: str,
    dimensions: dict[str, float],
    report: dict[str, Any],
    freshness_hours: float | None,
    sla_hours: float | None,
    impacted_assets: list[str],
) -> list[dict[str, Any]]:
    incidents: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    if (
        freshness_hours is not None
        and sla_hours is not None
        and freshness_hours > sla_hours
        and dimensions.get("freshness", 100) < 85
    ):
        delay = freshness_hours - sla_hours
        incidents.append(
            {
                "id": f"freshness-{table_name}",
                "title": f"{display_name} freshness issue",
                "summary": (
                    f"{display_name} delayed by {delay:.1f} hours "
                    f"(SLA expects refresh every {sla_hours:g} hours)."
                ),
                "severity": "high" if delay >= sla_hours else "medium",
                "status": "open",
                "dataset": table_name,
                "detectedAt": (now - timedelta(hours=min(delay, 48))).isoformat(),
                "impactedAssets": impacted_assets,
                "rootCauseHint": None,  # Omit when unknown — never guess.
                "blastRadius": {
                    "kpis": len([a for a in impacted_assets if a.startswith("kpi:")]),
                    "dashboards": len([a for a in impacted_assets if a.startswith("dashboard:")]),
                    "insights": len([a for a in impacted_assets if a.startswith("insight:")]),
                },
            }
        )

    if dimensions.get("completeness", 100) < 80:
        null_pct = float(report.get("total_null_pct") or 0)
        incidents.append(
            {
                "id": f"completeness-{table_name}",
                "title": f"{display_name} completeness warning",
                "summary": f"Sample null rate is {null_pct:.1f}%. Completeness score is depressed.",
                "severity": "medium" if null_pct < 10 else "high",
                "status": "open",
                "dataset": table_name,
                "detectedAt": now.isoformat(),
                "impactedAssets": impacted_assets,
                "rootCauseHint": None,
                "blastRadius": {
                    "kpis": len([a for a in impacted_assets if a.startswith("kpi:")]),
                    "dashboards": 1 if impacted_assets else 0,
                    "insights": 0,
                },
            }
        )

    if report.get("type_issues"):
        incidents.append(
            {
                "id": f"validity-{table_name}",
                "title": f"Validity findings on {display_name}",
                "summary": f"{len(report['type_issues'])} column type/validity issue(s) in sample.",
                "severity": "medium",
                "status": "open",
                "dataset": table_name,
                "detectedAt": now.isoformat(),
                "impactedAssets": impacted_assets[:4],
                "rootCauseHint": None,
                "blastRadius": {
                    "kpis": min(2, len(impacted_assets)),
                    "dashboards": 1,
                    "insights": 0,
                },
            }
        )

    if report.get("date_gaps"):
        incidents.append(
            {
                "id": f"gaps-{table_name}",
                "title": f"Date gaps in {display_name}",
                "summary": f"Missing periods: {', '.join(report['date_gaps'][:4])}.",
                "severity": "low",
                "status": "open",
                "dataset": table_name,
                "detectedAt": now.isoformat(),
                "impactedAssets": impacted_assets[:3],
                "rootCauseHint": None,
                "blastRadius": {"kpis": 1, "dashboards": 1, "insights": 0},
            }
        )

    return incidents


def build_rules_for_table(table_name: str, report: dict[str, Any], dimensions: dict[str, float]) -> list[dict[str, Any]]:
    """Surface DQ engine checks as manageable rules (pass/fail) — not a new engine."""
    now = datetime.now(UTC).isoformat()
    rules = [
        {
            "id": f"{table_name}-null-pct",
            "name": "Null percentage threshold",
            "dataset": table_name,
            "dimension": "completeness",
            "threshold": 5.0,
            "unit": "percent",
            "passing": float(report.get("total_null_pct") or 0) < 5.0,
            "observed": float(report.get("total_null_pct") or 0),
            "owner": "Data Platform",
            "lastModified": now,
            "editable": True,
        },
        {
            "id": f"{table_name}-duplicate-pct",
            "name": "Duplicate row threshold",
            "dataset": table_name,
            "dimension": "uniqueness",
            "threshold": 1.0,
            "unit": "percent",
            "passing": float(report.get("duplicate_pct") or 0) < 1.0,
            "observed": float(report.get("duplicate_pct") or 0),
            "owner": "Data Platform",
            "lastModified": now,
            "editable": True,
        },
        {
            "id": f"{table_name}-type-issues",
            "name": "No type/validity issues",
            "dataset": table_name,
            "dimension": "validity",
            "threshold": 0,
            "unit": "count",
            "passing": len(report.get("type_issues") or []) == 0,
            "observed": float(len(report.get("type_issues") or [])),
            "owner": "Data Platform",
            "lastModified": now,
            "editable": False,
        },
        {
            "id": f"{table_name}-date-gaps",
            "name": "No date gaps in grain",
            "dataset": table_name,
            "dimension": "consistency",
            "threshold": 0,
            "unit": "count",
            "passing": len(report.get("date_gaps") or []) == 0,
            "observed": float(len(report.get("date_gaps") or [])),
            "owner": "Data Platform",
            "lastModified": now,
            "editable": False,
        },
        {
            "id": f"{table_name}-freshness-sla",
            "name": "Freshness within SLA",
            "dataset": table_name,
            "dimension": "freshness",
            "threshold": dimensions.get("freshness", 0),
            "unit": "score",
            "passing": dimensions.get("freshness", 0) >= 85,
            "observed": dimensions.get("freshness", 0),
            "owner": "Data Platform",
            "lastModified": now,
            "editable": True,
        },
    ]
    return rules
