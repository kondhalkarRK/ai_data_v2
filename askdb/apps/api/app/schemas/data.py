"""Schemas for Data Preview and Data Quality (Phase 3)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import ApiModel, PageMeta


class PreviewTableSummary(ApiModel):
    name: str
    display_name: str
    physical_name: str
    table_type: str
    primary_key: str
    grain: str | None = None
    estimated_rows: int | None = None
    column_count: int


class PreviewColumn(ApiModel):
    name: str
    display_name: str
    type: str
    role: str


class PreviewRow(ApiModel):
    values: dict[str, Any]


class PreviewPage(ApiModel):
    table: str
    physical_name: str
    columns: list[PreviewColumn]
    items: list[PreviewRow]
    meta: PageMeta


class DataQualityReport(ApiModel):
    table: str
    physical_name: str
    sample_rows: int
    health_score: float
    total_rows: int
    total_cols: int
    total_null_pct: float
    duplicate_count: int
    duplicate_pct: float
    null_summary: dict[str, Any] = Field(default_factory=dict)
    outliers: dict[str, Any] = Field(default_factory=dict)
    type_issues: list[dict[str, Any]] = Field(default_factory=list)
    cardinality_flags: list[dict[str, Any]] = Field(default_factory=list)
    date_gaps: list[str] = Field(default_factory=list)
    date_col: str | None = None
    computed_in: str = "python"
