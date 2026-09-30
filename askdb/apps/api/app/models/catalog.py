"""Entity Catalog: refresh history, known values, schema baseline and detected changes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class CatalogRefresh(Base):
    __tablename__ = "catalog_refreshes"
    __table_args__ = (Index("ix_catalog_refreshes_industry_started", "industry", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_id: Mapped[str] = mapped_column(String(80), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(320))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_processed: Mapped[int | None] = mapped_column(BigInteger)
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_value_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ai_coverage: Mapped[float | None] = mapped_column(Float)
    stats: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class CatalogValue(Base):
    __tablename__ = "catalog_values"
    __table_args__ = (
        UniqueConstraint("industry", "domain_key", "value", name="uq_catalog_values_value"),
        Index("ix_catalog_values_industry_domain", "industry", "domain_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    domain_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    frequency: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_load: Mapped[str] = mapped_column(String(80), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Values present in the domain's first refresh are the baseline, never "new".
    baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CatalogColumn(Base):
    __tablename__ = "catalog_columns"
    __table_args__ = (
        UniqueConstraint("industry", "table_name", "column_name", name="uq_catalog_columns_column"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    table_name: Mapped[str] = mapped_column(String(160), nullable=False)
    column_name: Mapped[str] = mapped_column(String(120), nullable=False)
    data_type: Mapped[str] = mapped_column(String(60), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogChange(Base):
    __tablename__ = "catalog_changes"
    __table_args__ = (Index("ix_catalog_changes_industry_detected", "industry", "detected_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    refresh_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="low")
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(160))
    column_name: Mapped[str | None] = mapped_column(String(120))
    domain_key: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    impact: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
