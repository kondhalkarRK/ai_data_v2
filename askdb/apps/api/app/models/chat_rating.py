"""Owner-scoped feedback references the existing stable query-history response ID."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChatRating(Base):
    __tablename__ = "chat_ratings"

    response_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_history.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_users.user_id"), primary_key=True
    )
    rating: Mapped[str] = mapped_column(String(4))
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bi_reports.id"), nullable=True
    )
    report_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("rating IN ('up', 'down')", name="rating_value"),
        CheckConstraint(
            "reason IS NULL OR reason IN "
            "('incorrect', 'misunderstood', 'incomplete', 'unclear', 'other')",
            name="rating_reason",
        ),
        CheckConstraint("note IS NULL OR length(note) <= 2000", name="rating_note_length"),
    )
