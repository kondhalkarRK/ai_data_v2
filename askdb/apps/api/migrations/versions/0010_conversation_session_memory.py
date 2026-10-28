"""Add compact session memory on conversations (additive, nullable).

Revision ID: 0010_conversation_session_memory
Revises: 0009_user_region_access
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_conversation_session_memory"
down_revision: str | None = "0009_user_region_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("session_memory", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "session_memory")
