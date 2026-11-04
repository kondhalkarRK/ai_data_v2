"""Owner-scoped analytics definitions; warehouse rows are never persisted."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JsonDocument


class AnalyticsWorkspace(Base):
    __tablename__ = "analytics_workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.user_id"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    scope_key: Mapped[str] = mapped_column(String(500))
    semantic_revision: Mapped[str] = mapped_column(String(200))
    definition: Mapped[dict[str, Any]] = mapped_column(JsonDocument)
    messages: Mapped[list[dict[str, str]]] = mapped_column(JsonDocument, default=list)
