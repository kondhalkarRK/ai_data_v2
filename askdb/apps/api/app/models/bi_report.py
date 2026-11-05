"""Owned BI drafts/conversations; analytical result rows are never stored here."""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class BiReportRecord(Base):
    __tablename__ = "bi_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.user_id"), index=True
    )
    title: Mapped[str] = mapped_column(String(160), default="Untitled report")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    scope_key: Mapped[str] = mapped_column(String(600))
    semantic_revision: Mapped[str] = mapped_column(String(200))
    state: Mapped[dict[str, Any]] = mapped_column(JsonDocument, default=dict)
    requests: Mapped[list[dict[str, Any]]] = mapped_column(JsonDocument, default=list)
