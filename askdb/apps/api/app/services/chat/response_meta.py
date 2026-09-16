"""Honest response metadata for the chat UI — never invent certainty."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import Industry

GroundedSource = Literal[
    "Semantic Layer",
    "Business Glossary",
    "KPI Definition",
    "Data Quality Check",
]

ValidationStatus = Literal["passed", "auto_repaired", "failed", "skipped"]


@dataclass
class QueryTimings:
    llm_generation_ms: int = 0
    semantic_lookup_ms: int = 0
    sql_validation_ms: int = 0
    sql_auto_repair_ms: int = 0
    execution_ms: int = 0
    render_ms: int = 0

    def to_dict(self) -> dict[str, int]:
        payload = {
            "llmGenerationMs": self.llm_generation_ms,
            "semanticLookupMs": self.semantic_lookup_ms,
            "sqlValidationMs": self.sql_validation_ms,
            "executionMs": self.execution_ms,
            "renderMs": self.render_ms,
        }
        if self.sql_auto_repair_ms:
            payload["sqlAutoRepairMs"] = self.sql_auto_repair_ms
        return payload


@dataclass
class QueryMeta:
    tables_used: list[str] = field(default_factory=list)
    metrics_used: list[str] = field(default_factory=list)
    dimensions_used: list[str] = field(default_factory=list)
    join_path: list[str] = field(default_factory=list)
    filters_applied: list[str] = field(default_factory=list)
    date_range: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tablesUsed": self.tables_used,
            "metricsUsed": self.metrics_used,
            "dimensionsUsed": self.dimensions_used,
            "joinPath": self.join_path,
            "filtersApplied": self.filters_applied,
            "dateRange": self.date_range,
        }


_TABLE_RE = re.compile(
    r"\b(?:from|join)\s+([a-z_][\w]*(?:\.[a-z_][\w]*)?)",
    re.IGNORECASE,
)
_FILTER_RE = re.compile(
    r"\bwhere\b(.+?)(?:\bgroup\b|\border\b|\blimit\b|$)",
    re.IGNORECASE | re.DOTALL,
)
_DATE_RE = re.compile(
    r"(?:>=|<=|=|>|<)\s*(?:DATE\s+)?'(\d{4}-\d{2}-\d{2})'",
    re.IGNORECASE,
)


def extract_query_meta(sql: str | None) -> QueryMeta:
    if not sql:
        return QueryMeta()
    tables = list(dict.fromkeys(m.group(1) for m in _TABLE_RE.finditer(sql)))
    joins = [t for t in tables[1:]] if len(tables) > 1 else []
    filters: list[str] = []
    filter_match = _FILTER_RE.search(sql)
    if filter_match:
        raw = re.sub(r"\s+", " ", filter_match.group(1)).strip(" ;")
        if raw:
            filters.append(raw[:180])
    dates = _DATE_RE.findall(sql)
    date_range = " → ".join(dates) if dates else None
    # Heuristic metric/dimension column names from SELECT list
    select_match = re.search(r"select\s+(.*?)\s+from\b", sql, re.IGNORECASE | re.DOTALL)
    metrics: list[str] = []
    dimensions: list[str] = []
    if select_match:
        parts = [p.strip() for p in select_match.group(1).split(",")]
        for part in parts:
            alias = re.split(r"\s+as\s+", part, flags=re.IGNORECASE)
            name = alias[-1].strip().split(".")[-1].strip('"')
            if re.search(r"\b(sum|avg|count|min|max)\s*\(", part, re.IGNORECASE):
                metrics.append(name)
            elif name and name.lower() not in {"*", "1"}:
                dimensions.append(name)
    return QueryMeta(
        tables_used=tables,
        metrics_used=metrics[:8],
        dimensions_used=dimensions[:8],
        join_path=joins,
        filters_applied=filters,
        date_range=date_range,
    )


def resolve_grounded_on(
    *,
    path: str,
    glossary_matches: int,
    has_sql: bool,
    dq_checked: bool,
) -> list[GroundedSource]:
    grounded: list[GroundedSource] = []
    if path in {"template", "semantic", "semantic_llm"} or has_sql:
        grounded.append("Semantic Layer")
    if glossary_matches > 0:
        grounded.append("Business Glossary")
    if path == "template" or (has_sql and glossary_matches >= 1):
        grounded.append("KPI Definition")
    if dq_checked:
        grounded.append("Data Quality Check")
    return grounded


def build_insights(
    *,
    narrative: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    path: str,
) -> dict[str, str]:
    """Derive executive vs analyst depth from real result shape — no invented KPIs."""
    n = len(rows)
    if n == 0:
        executive = (
            narrative.strip()
            or "The query completed but returned no rows for the current filters."
        )
        analyst = (
            f"{executive} Consider widening the date range or removing a filter."
        )
        return {"executive": executive[:520], "analyst": analyst[:900]}

    # Prefer business storytelling over SQL-path commentary.
    story = _business_story(columns, rows)
    base = narrative.strip()
    if story:
        executive = f"{base.rstrip('.')}. {story}".strip() if base else story
    elif base:
        executive = f"{base.rstrip('.')} Across {n} result rows."
    else:
        executive = f"Returned {n} row{'s' if n != 1 else ''} across {len(columns)} fields."

    analyst_parts = [executive]
    first_cols = columns[:3]
    if rows and first_cols:
        head = rows[0]
        sample_bits = [f"{col}={head.get(col)}" for col in first_cols if col in head]
        if sample_bits:
            analyst_parts.append("Leading row: " + ", ".join(str(b) for b in sample_bits) + ".")
    if len(columns) >= 2 and rows:
        y_key = columns[1]
        numeric: list[float] = []
        for row in rows:
            try:
                numeric.append(float(row[y_key]))  # type: ignore[arg-type]
            except (TypeError, ValueError, KeyError):
                continue
        if len(numeric) >= 3:
            peak = max(numeric)
            trough = min(numeric)
            mean = sum(numeric) / len(numeric)
            analyst_parts.append(
                f"On {y_key.replace('_', ' ')}: range {trough:g}–{peak:g}, "
                f"average {mean:g} across {len(numeric)} points."
            )
            # Highlight simple anomalies relative to mean
            outliers = [v for v in numeric if abs(v - mean) >= max(mean * 0.35, 1e-9)]
            if outliers and len(numeric) >= 5:
                analyst_parts.append(
                    f"{len(outliers)} value(s) sit notably above or below the series average."
                )
    return {
        "executive": executive[:520],
        "analyst": " ".join(analyst_parts)[:900],
    }


def _business_story(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """Plain-language highlights: leaders, share, and simple comparisons."""
    if not columns or not rows:
        return ""
    label_key = columns[0]
    value_key = None
    for col in columns[1:]:
        try:
            float(rows[0].get(col))  # type: ignore[arg-type]
            value_key = col
            break
        except (TypeError, ValueError):
            continue
    if value_key is None:
        leaders = [
            str(row.get(label_key) or "")
            for row in rows[:3]
            if row.get(label_key) is not None
        ]
        if leaders:
            return f"Top results include {', '.join(leaders)}."
        return ""

    scored: list[tuple[str, float]] = []
    for row in rows:
        label = row.get(label_key)
        if label is None:
            continue
        try:
            scored.append((str(label), float(row[value_key])))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    if not scored:
        return ""
    scored.sort(key=lambda item: item[1], reverse=True)
    total = sum(v for _, v in scored) or 0.0
    top_name, top_value = scored[0]
    parts = [
        f"{top_name} led with {_fmt(top_value)} {_friendly(value_key)}"
        + (f" ({top_value / total:.0%} of the total)." if total > 0 and len(scored) > 1 else ".")
    ]
    if len(scored) >= 2:
        second_name, second_value = scored[1]
        parts.append(
            f"{second_name} followed at {_fmt(second_value)}"
            + (f" ({second_value / total:.0%})." if total > 0 else ".")
        )
    if len(scored) >= 3 and total > 0:
        top3 = sum(v for _, v in scored[:3])
        parts.append(f"The top three together account for {top3 / total:.0%} of the result set.")
    return " ".join(parts)


def _friendly(column: str) -> str:
    return column.replace("_", " ").strip()


def _fmt(value: float) -> str:
    if abs(value) >= 10_000_000:
        return f"{value / 10_000_000:.1f}Cr"
    if abs(value) >= 100_000:
        return f"{value / 100_000:.1f}L"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return f"{int(value)}"
    return f"{value:.2f}"


def detect_anomalies(
    columns: list[str],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mark simple statistical outliers on the first numeric series (UI-ready)."""
    if len(columns) < 2 or len(rows) < 5:
        return []
    x_key, y_key = columns[0], columns[1]
    points: list[tuple[int, float]] = []
    for index, row in enumerate(rows[:40]):
        try:
            points.append((index, float(row[y_key])))  # type: ignore[arg-type]
        except (TypeError, ValueError, KeyError):
            continue
    if len(points) < 5:
        return []
    values = [v for _, v in points]
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    std = var**0.5
    if std <= 0:
        return []
    markers: list[dict[str, Any]] = []
    for index, value in points:
        z = (value - mean) / std
        if abs(z) >= 2.0:
            markers.append(
                {
                    "index": index,
                    "x": rows[index].get(x_key),
                    "y": value,
                    "zScore": round(z, 2),
                    "direction": "spike" if z > 0 else "dip",
                    "label": f"{'Spike' if z > 0 else 'Dip'} vs series mean",
                }
            )
    return markers[:5]


def sql_diff_lines(prior: str | None, current: str | None) -> list[dict[str, str]] | None:
    if not prior or not current or prior.strip() == current.strip():
        return None
    diff = difflib.unified_diff(
        prior.strip().splitlines(),
        current.strip().splitlines(),
        fromfile="previous",
        tofile="current",
        lineterm="",
    )
    lines: list[dict[str, str]] = []
    for line in diff:
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines.append({"op": "add", "text": line[1:]})
        elif line.startswith("-"):
            lines.append({"op": "del", "text": line[1:]})
        else:
            lines.append({"op": "ctx", "text": line[1:] if line.startswith(" ") else line})
    return lines[:80] or None


def semantic_followups(
    industry: Industry,
    *,
    dimensions: list[str],
    metrics: list[str],
    tables: list[str],
    path: str,
) -> list[str]:
    """Build follow-ups only from dimensions/metrics actually present in this query."""
    suggestions: list[str] = []
    dim_l = [d.lower() for d in dimensions]
    table_blob = " ".join(tables).lower()

    def has(*tokens: str) -> bool:
        return any(token in dim_l or token in table_blob for token in tokens)

    if industry is Industry.INSURANCE:
        if has("region", "region_name", "dim_region"):
            suggestions.append("Break this down by region")
        if has("month", "accounting_month", "reported_date"):
            suggestions.append("Show the monthly trend")
        if any("claim" in m.lower() or "premium" in m.lower() for m in metrics + tables):
            suggestions.append("Compare claim count and premium")
        if not suggestions:
            suggestions = ["Show loss ratio", "Show claims by status", "Show premium by month"]
    else:
        if has("dealer", "dealer_name", "dim_dealer"):
            suggestions.append("Break this down by dealer")
        if has("month", "sales_date", "year"):
            suggestions.append("Show the monthly trend")
        if has("model", "make", "carline"):
            suggestions.append("Compare the top models")
        if not suggestions:
            suggestions = ["Show revenue by month", "Show top models", "Show EV share"]

    if path == "out_of_bounds":
        return (
            ["Show loss ratio", "Show claims by status", "Show premium by month"]
            if industry is Industry.INSURANCE
            else ["Show revenue by month", "Show top models", "Show EV share"]
        )
    return suggestions[:3]


def source_database_label(industry: Industry) -> str:
    if industry is Industry.INSURANCE:
        return "PostgreSQL · askdb_insurance"
    return "PostgreSQL · askdb_automotive"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()
