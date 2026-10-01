"""Data Reliability Center: rule settings, custom monitors, run history and score snapshots."""

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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class DqRuleSetting(Base):
    """Overrides for a built-in rule, or the full definition of a custom monitor."""

    __tablename__ = "dq_rule_settings"
    __table_args__ = (UniqueConstraint("industry", "rule_id", name="uq_dq_rule_settings_rule"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(120), nullable=False)
    custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    overrides: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DqRuleRun(Base):
    __tablename__ = "dq_rule_runs"
    __table_args__ = (Index("ix_dq_rule_runs_industry_ran", "industry", "ran_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    rule_id: Mapped[str] = mapped_column(String(120), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    pass_rate: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    value_at_risk: Mapped[float | None] = mapped_column(Float)


class DqScoreSnapshot(Base):
    __tablename__ = "dq_score_snapshots"
    __table_args__ = (Index("ix_dq_score_snapshots_industry_ran", "industry", "ran_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    industry: Mapped[str] = mapped_column(String(20), nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    datasets: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    rules_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_passing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rules_failing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triggered_by: Mapped[str | None] = mapped_column(String(320))
