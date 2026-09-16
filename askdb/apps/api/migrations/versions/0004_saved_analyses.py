"""Saved analyses table for Analytics Builder metadata."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_saved_analyses"
down_revision: str | None = "0003_insight_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("viz", sa.String(length=40), server_default="auto", nullable=False),
        sa.Column("sql_snapshot", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_analyses_user_id", "saved_analyses", ["user_id"])
    op.create_index(
        "ix_saved_analyses_user_industry",
        "saved_analyses",
        ["user_id", "industry"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_analyses_user_industry", table_name="saved_analyses")
    op.drop_index("ix_saved_analyses_user_id", table_name="saved_analyses")
    op.drop_table("saved_analyses")
