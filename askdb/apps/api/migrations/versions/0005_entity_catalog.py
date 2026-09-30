"""Entity Catalog: refresh history, catalogued values, schema baseline, detected changes."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_entity_catalog"
down_revision: str | None = "0004_saved_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts(name: str, *, nullable: bool = False, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default_now else None,
        nullable=nullable,
    )


def _json(name: str) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'{}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "catalog_refreshes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("load_id", sa.String(length=80), nullable=False),
        sa.Column("requested_by", sa.String(length=320), nullable=True),
        _ts("started_at", default_now=True),
        _ts("finished_at", nullable=True),
        sa.Column("rows_processed", sa.BigInteger(), nullable=True),
        sa.Column("entity_count", sa.Integer(), nullable=False),
        sa.Column("new_value_count", sa.Integer(), nullable=False),
        sa.Column("change_count", sa.Integer(), nullable=False),
        sa.Column("ai_coverage", sa.Float(), nullable=True),
        _json("stats"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_refreshes"),
    )
    op.create_index(
        "ix_catalog_refreshes_industry_started", "catalog_refreshes", ["industry", "started_at"]
    )

    op.create_table(
        "catalog_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("domain_key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("frequency", sa.BigInteger(), nullable=False),
        _ts("first_seen_at"),
        sa.Column("first_seen_load", sa.String(length=80), nullable=False),
        _ts("last_seen_at"),
        sa.Column("baseline", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_values"),
        sa.UniqueConstraint("industry", "domain_key", "value", name="uq_catalog_values_value"),
    )
    op.create_index(
        "ix_catalog_values_industry_domain", "catalog_values", ["industry", "domain_key"]
    )

    op.create_table(
        "catalog_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("table_name", sa.String(length=160), nullable=False),
        sa.Column("column_name", sa.String(length=120), nullable=False),
        sa.Column("data_type", sa.String(length=60), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        _ts("first_seen_at"),
        _ts("last_seen_at"),
        _ts("removed_at", nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_columns"),
        sa.UniqueConstraint(
            "industry", "table_name", "column_name", name="uq_catalog_columns_column"
        ),
    )

    op.create_table(
        "catalog_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("refresh_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("table_name", sa.String(length=160), nullable=True),
        sa.Column("column_name", sa.String(length=120), nullable=True),
        sa.Column("domain_key", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        _json("detail"),
        _json("impact"),
        _ts("detected_at"),
        sa.PrimaryKeyConstraint("id", name="pk_catalog_changes"),
    )
    op.create_index(
        "ix_catalog_changes_industry_detected", "catalog_changes", ["industry", "detected_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_changes_industry_detected", table_name="catalog_changes")
    op.drop_table("catalog_changes")
    op.drop_table("catalog_columns")
    op.drop_index("ix_catalog_values_industry_domain", table_name="catalog_values")
    op.drop_table("catalog_values")
    op.drop_index("ix_catalog_refreshes_industry_started", table_name="catalog_refreshes")
    op.drop_table("catalog_refreshes")
