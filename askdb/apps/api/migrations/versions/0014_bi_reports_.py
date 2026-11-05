"""AskBI owned report drafts, conversation state and idempotency receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_bi_reports"
down_revision = "0013_analytics_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bi_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_users.user_id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("scope_key", sa.String(600), nullable=False),
        sa.Column("semantic_revision", sa.String(200), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("requests", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_bi_reports_user_id", "bi_reports", ["user_id"])


def downgrade() -> None:
    op.drop_table("bi_reports")
