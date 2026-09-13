"""Insight feedback table for Executive Intelligence human-in-the-loop signals."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_insight_feedback"
down_revision: str | None = "0002_activity_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "insight_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("industry", sa.String(length=20), nullable=False),
        sa.Column("insight_id", sa.String(length=120), nullable=False),
        sa.Column("vote", sa.String(length=8), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("grounded_on", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_insight_feedback_user_id", "insight_feedback", ["user_id"])
    op.create_index("ix_insight_feedback_insight_id", "insight_feedback", ["insight_id"])


def downgrade() -> None:
    op.drop_index("ix_insight_feedback_insight_id", table_name="insight_feedback")
    op.drop_index("ix_insight_feedback_user_id", table_name="insight_feedback")
    op.drop_table("insight_feedback")
