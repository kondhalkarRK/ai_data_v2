"""PoC governance tables: login audit, admin audit and runtime settings."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class LoginAudit(Base):
    """One row per sign-in attempt; ``logout_time`` is filled when that session ends."""

    __tablename__ = "login_audit"

    id: Mapped[uuid.UUID] = mapped_column("audit_id", primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    # The name typed on the login form, kept for failed attempts against unknown accounts.
    username: Mapped[str | None] = mapped_column(String(320), nullable=True)
    login_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # SUCCESS | FAILED | LOGOUT

    __table_args__ = (
        Index("ix_login_audit_user_time", "user_id", "login_time"),
        CheckConstraint("status IN ('SUCCESS', 'FAILED', 'LOGOUT')", name="status"),
    )


class AdminAudit(Base):
    """Key platform actions shown in the Admin Center audit view."""

    __tablename__ = "admin_audit"

    id: Mapped[uuid.UUID] = mapped_column("audit_id", primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    action_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_action_created", "action", "created_at"),
    )


class AppSetting(Base):
    """Admin-editable runtime settings (e.g. the active LLM provider and model)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
