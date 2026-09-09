"""Phase 5/6 application tables: conversations, history, saved questions, LLM usage."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_activity_schema"
down_revision: str | None = "0001_app_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDUSTRIES = ("automotive", "insurance")
QUERY_STATUSES = ("completed", "cancelled", "failed", "running")


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "industry",
            sa.Enum(*INDUSTRIES, name="conversation_industry", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_conversations_user"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index("ix_conversations_user_updated", "conversations", ["user_id", "updated_at"])

    op.create_table(
        "query_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "industry",
            sa.Enum(*INDUSTRIES, name="history_industry", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*QUERY_STATUSES, name="query_status", native_enum=False, length=20),
            server_default="completed",
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("trust_score", sa.Integer(), nullable=True),
        sa.Column("trust_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_history_user"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], name="fk_history_conversation"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_history"),
    )
    op.create_index("ix_history_user_created", "query_history", ["user_id", "created_at"])

    op.create_table(
        "saved_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "industry",
            sa.Enum(*INDUSTRIES, name="saved_industry", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_saved_user"),
        sa.PrimaryKeyConstraint("id", name="pk_saved_questions"),
    )
    op.create_index("ix_saved_user_industry", "saved_questions", ["user_id", "industry"])

    op.create_table(
        "llm_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("industry", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completion_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_llm_usage_user"),
        sa.PrimaryKeyConstraint("id", name="pk_llm_usage"),
    )
    op.create_index("ix_llm_usage_created", "llm_usage", ["created_at"])


def downgrade() -> None:
    op.drop_table("llm_usage")
    op.drop_table("saved_questions")
    op.drop_table("query_history")
    op.drop_table("conversations")
