"""Row-level region grants (``user_region_access``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRegionAccess(Base):
    """Zones a user may read. An empty set for ``admin`` means every zone."""

    __tablename__ = "user_region_access"

    id: Mapped[uuid.UUID] = mapped_column("user_region_id", primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_users.user_id", ondelete="CASCADE"), nullable=False
    )
    # Zone name (North / South / East / West), not a warehouse region_id — those differ
    # by industry and live in another database.
    region_id: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "region_id", name="uq_user_region_access_user_region"),
        Index("ix_user_region_access_user_id", "user_id"),
    )
