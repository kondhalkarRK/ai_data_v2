"""Automotive Auto boards. Specifications only; never durable cached warehouse rows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class AutoDashboard(Base):
    __tablename__ = "auto_dashboards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.user_id"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_key: Mapped[str] = mapped_column(String(500))
    definition: Mapped[dict[str, Any]] = mapped_column(JsonDocument)
    previous: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
