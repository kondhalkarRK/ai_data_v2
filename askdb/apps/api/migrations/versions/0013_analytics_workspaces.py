"""Unified automotive analytics definitions. No existing saved content is changed."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_analytics_workspaces"
down_revision = "0012_auto_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_users.user_id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("scope_key", sa.String(500), nullable=False),
        sa.Column("semantic_revision", sa.String(200), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("messages", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_analytics_workspaces_user_id", "analytics_workspaces", ["user_id"])


def downgrade() -> None:
    op.drop_table("analytics_workspaces")
