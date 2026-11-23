"""Durable Chat response replay and editable owner ratings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_chat_response_ratings"
down_revision = "0014_bi_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "query_history", sa.Column("response_snapshot", postgresql.JSONB(), nullable=True)
    )
    op.create_table(
        "chat_ratings",
        sa.Column(
            "response_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("query_history.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_users.user_id"),
            primary_key=True,
        ),
        sa.Column("rating", sa.String(4), nullable=False),
        sa.Column("reason", sa.String(40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bi_reports.id"),
            nullable=True,
        ),
        sa.Column("report_revision", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rating IN ('up', 'down')", name="rating_value"),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ('incorrect', 'misunderstood', 'incomplete', 'unclear', 'other')",
            name="rating_reason",
        ),
        sa.CheckConstraint("note IS NULL OR length(note) <= 2000", name="rating_note_length"),
    )


def downgrade() -> None:
    op.drop_table("chat_ratings")
    op.drop_column("query_history", "response_snapshot")
