"""Owner-scoped automotive Auto board specifications.

Revision ID: 0012_auto_dashboards
Revises: 0011_knowledge_documents
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_auto_dashboards"
down_revision = "0011_knowledge_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auto_dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("auth_users.user_id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("saved", sa.Boolean(), nullable=False),
        sa.Column("scope_key", sa.String(500), nullable=False),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("previous", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_auto_dashboards_user_id", "auto_dashboards", ["user_id"])


def downgrade() -> None:
    op.drop_table("auto_dashboards")
