"""Region row-level access grants (``user_region_access``).

Revision ID: 0009_user_region_access
Revises: 0008_fix_user_role_enum
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_user_region_access"
down_revision: str | None = "0008_fix_user_role_enum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_region_access",
        sa.Column("user_region_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_id", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.user_id"],
            name="fk_user_region_access_user_id_auth_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_region_id", name="pk_user_region_access"),
        sa.UniqueConstraint("user_id", "region_id", name="uq_user_region_access_user_region"),
    )
    op.create_index("ix_user_region_access_user_id", "user_region_access", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_region_access_user_id", table_name="user_region_access")
    op.drop_table("user_region_access")
