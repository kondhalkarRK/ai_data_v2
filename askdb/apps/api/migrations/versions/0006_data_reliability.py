"""Data Reliability Center: rule settings, custom monitors, run history, score snapshots.

Revision ID: 0006_data_reliability
Revises: 0005_entity_catalog
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_data_reliability"
down_revision: str | None = "0005_entity_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "dq_rule_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("rule_id", sa.String(length=120), nullable=False),
        sa.Column("custom", sa.Boolean(), nullable=False),
        _json("definition"),
        _json("overrides"),
        sa.Column("created_by", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dq_rule_settings"),
        sa.UniqueConstraint("industry", "rule_id", name="uq_dq_rule_settings_rule"),
    )

    op.create_table(
        "dq_rule_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", sa.String(length=120), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("total", sa.BigInteger(), nullable=False),
        sa.Column("failed", sa.BigInteger(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("value_at_risk", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_dq_rule_runs"),
    )
    op.create_index("ix_dq_rule_runs_industry_ran", "dq_rule_runs", ["industry", "ran_at"])

    op.create_table(
        "dq_score_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        _json("dimensions"),
        _json("datasets"),
        sa.Column("rules_total", sa.Integer(), nullable=False),
        sa.Column("rules_passing", sa.Integer(), nullable=False),
        sa.Column("rules_failing", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(length=320), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_dq_score_snapshots"),
    )
    op.create_index(
        "ix_dq_score_snapshots_industry_ran", "dq_score_snapshots", ["industry", "ran_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_dq_score_snapshots_industry_ran", table_name="dq_score_snapshots")
    op.drop_table("dq_score_snapshots")
    op.drop_index("ix_dq_rule_runs_industry_ran", table_name="dq_rule_runs")
    op.drop_table("dq_rule_runs")
    op.drop_table("dq_rule_settings")
