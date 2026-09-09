"""Anonymous session identity — no user authentication in this project."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class UserSession(UUIDPKMixin, TimestampMixin, Base):
    """An anonymous browser/device session, identified by an opaque UUID."""

    __tablename__ = "user_sessions"

    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
