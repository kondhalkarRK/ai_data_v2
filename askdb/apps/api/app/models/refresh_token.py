"""Refresh token model.

Refresh tokens rotate on every use. Only a SHA-256 digest is stored, so a database dump
cannot be replayed against the API. Tokens are grouped into a *family*: rotating a token
creates a successor in the same family, and presenting an already-rotated token revokes
the entire family, which is the standard defence against refresh-token theft.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import ensure_aware
from app.models.base import Base, IPAddress, UUIDPrimaryKeyMixin


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Identifies the chain of rotations that started at one login.
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False)

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Set when this token is exchanged for a successor.
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the token is invalidated by logout or by family revocation.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))

    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(IPAddress)

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    def is_usable(self, now: datetime) -> bool:
        return (
            self.revoked_at is None
            and self.rotated_at is None
            and ensure_aware(self.expires_at) > ensure_aware(now)
        )
