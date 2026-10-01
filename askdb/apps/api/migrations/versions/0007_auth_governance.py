"""PoC authentication and governance: ADMIN/USER roles, quotas, login and admin audit.

* ``users`` becomes ``auth_users`` (``user_id``, ``username``, ``active``, ``last_login``,
  weekly token / call limits). Existing ``analyst`` and ``viewer`` accounts become ``user``.
* ``llm_usage`` becomes one row per AI Chat question with its execution mode.
* New ``login_audit``, ``admin_audit`` and ``app_settings`` tables.

The standalone equivalent for DBAs is ``database/app/10_auth_governance.sql``.

Revision ID: 0007_auth_governance
Revises: 0006_data_reliability
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_auth_governance"
down_revision: str | None = "0006_data_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    # --- auth_users ---------------------------------------------------------
    op.rename_table("users", "auth_users")
    op.alter_column("auth_users", "id", new_column_name="user_id")
    op.alter_column("auth_users", "is_active", new_column_name="active")
    op.alter_column("auth_users", "last_login_at", new_column_name="last_login")
    op.execute("ALTER TABLE auth_users RENAME CONSTRAINT pk_users TO pk_auth_users")
    op.execute(
        "ALTER TABLE auth_users RENAME CONSTRAINT uq_users_email_normalized "
        "TO uq_auth_users_email_normalized"
    )
    op.drop_index("ix_users_role_active", table_name="auth_users")
    op.create_index("ix_auth_users_role_active", "auth_users", ["role", "active"])

    # Existing accounts sign in with their email as the username (always unique); the
    # PoC seed adds the short ``admin`` / ``user1`` names.
    op.add_column("auth_users", sa.Column("username", sa.String(length=80), nullable=True))
    op.execute("UPDATE auth_users SET username = left(email_normalized, 80)")
    op.alter_column("auth_users", "username", nullable=False)
    op.create_unique_constraint("uq_auth_users_username", "auth_users", ["username"])

    op.execute("UPDATE auth_users SET role = 'user' WHERE role IN ('analyst', 'viewer')")
    op.alter_column("auth_users", "role", server_default="user")

    op.add_column(
        "auth_users",
        sa.Column("weekly_token_limit", sa.Integer(), server_default="60000", nullable=True),
    )
    op.add_column(
        "auth_users",
        sa.Column("weekly_call_limit", sa.Integer(), server_default="50", nullable=True),
    )
    op.execute(
        "UPDATE auth_users SET weekly_token_limit = NULL, weekly_call_limit = NULL "
        "WHERE role = 'admin'"
    )

    # --- llm_usage ----------------------------------------------------------
    op.alter_column("llm_usage", "id", new_column_name="usage_id")
    op.alter_column("llm_usage", "model", new_column_name="model_name")
    op.alter_column("llm_usage", "purpose", server_default="chat")
    op.add_column("llm_usage", sa.Column("question", sa.Text(), nullable=True))
    op.add_column(
        "llm_usage",
        sa.Column("execution_mode", sa.String(length=10), server_default="LLM", nullable=False),
    )
    op.add_column("llm_usage", sa.Column("response_time_ms", sa.Integer(), nullable=True))
    op.add_column(
        "llm_usage", sa.Column("query_history_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_llm_usage_execution_mode"),
        "llm_usage",
        "execution_mode IN ('SCHEMA', 'LLM', 'HYBRID', 'CACHE')",
    )
    op.create_index("ix_llm_usage_user_created", "llm_usage", ["user_id", "created_at"])
    op.create_index("ix_llm_usage_mode_created", "llm_usage", ["execution_mode", "created_at"])

    # --- login_audit --------------------------------------------------------
    op.create_table(
        "login_audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(length=320), nullable=True),
        sa.Column("login_time", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("logout_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCESS', 'FAILED', 'LOGOUT')", name=op.f("ck_login_audit_status")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.user_id"],
            name="fk_login_audit_user_id_auth_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("audit_id", name="pk_login_audit"),
    )
    op.create_index("ix_login_audit_user_time", "login_audit", ["user_id", "login_time"])

    # --- admin_audit --------------------------------------------------------
    op.create_table(
        "admin_audit",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("action_details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.user_id"],
            name="fk_admin_audit_user_id_auth_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("audit_id", name="pk_admin_audit"),
    )
    op.create_index("ix_admin_audit_created", "admin_audit", ["created_at"])
    op.create_index("ix_admin_audit_action_created", "admin_audit", ["action", "created_at"])

    # --- app_settings -------------------------------------------------------
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["auth_users.user_id"],
            name="fk_app_settings_updated_by_auth_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_index("ix_admin_audit_action_created", table_name="admin_audit")
    op.drop_index("ix_admin_audit_created", table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_index("ix_login_audit_user_time", table_name="login_audit")
    op.drop_table("login_audit")

    op.drop_index("ix_llm_usage_mode_created", table_name="llm_usage")
    op.drop_index("ix_llm_usage_user_created", table_name="llm_usage")
    op.drop_constraint(op.f("ck_llm_usage_execution_mode"), "llm_usage", type_="check")
    op.drop_column("llm_usage", "query_history_id")
    op.drop_column("llm_usage", "response_time_ms")
    op.drop_column("llm_usage", "execution_mode")
    op.drop_column("llm_usage", "question")
    op.alter_column("llm_usage", "purpose", server_default=None)
    op.alter_column("llm_usage", "model_name", new_column_name="model")
    op.alter_column("llm_usage", "usage_id", new_column_name="id")

    op.drop_column("auth_users", "weekly_call_limit")
    op.drop_column("auth_users", "weekly_token_limit")
    op.alter_column("auth_users", "role", server_default="viewer")
    op.execute("UPDATE auth_users SET role = 'analyst' WHERE role = 'user'")
    op.drop_constraint("uq_auth_users_username", "auth_users", type_="unique")
    op.drop_column("auth_users", "username")
    op.drop_index("ix_auth_users_role_active", table_name="auth_users")
    op.execute(
        "ALTER TABLE auth_users RENAME CONSTRAINT uq_auth_users_email_normalized "
        "TO uq_users_email_normalized"
    )
    op.execute("ALTER TABLE auth_users RENAME CONSTRAINT pk_auth_users TO pk_users")
    op.alter_column("auth_users", "last_login", new_column_name="last_login_at")
    op.alter_column("auth_users", "active", new_column_name="is_active")
    op.alter_column("auth_users", "user_id", new_column_name="id")
    op.rename_table("auth_users", "users")
    op.create_index("ix_users_role_active", "users", ["role", "is_active"])
