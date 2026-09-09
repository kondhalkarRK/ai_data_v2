"""Authentication audit trail.

Records who attempted what, from where, and whether it succeeded. Passwords, tokens and
prompts never appear here (spec section 18).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IPAddress, JsonDocument, UUIDPrimaryKeyMixin
from app.models.enums import AuthEventType


class AuthAuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "auth_audit_events"

    event_type: Mapped[AuthEventType] = mapped_column(
        Enum(AuthEventType, name="auth_event_type", native_enum=False, length=40),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Null when the attempt referenced an address with no matching account. The email is
    # still recorded so repeated probing is visible.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    email_attempted: Mapped[str | None] = mapped_column(String(320))

    request_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(IPAddress)
    user_agent: Mapped[str | None] = mapped_column(String(400))

    succeeded: Mapped[bool] = mapped_column(nullable=False)
    # Short machine-readable reason, never free-form user input.
    reason: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)

    __table_args__ = (
        Index("ix_auth_audit_user_time", "user_id", "occurred_at"),
        Index("ix_auth_audit_type_time", "event_type", "occurred_at"),
        Index("ix_auth_audit_email_time", "email_attempted", "occurred_at"),
    )
