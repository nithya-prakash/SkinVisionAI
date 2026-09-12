"""A registered user's workspace -- every analysis/product/routine/chat
this user creates hangs off their one UserSession row. Pre-auth, this
was an anonymous, unowned session; ``user_id`` is what changed (see
app.services.auth_service / docs/persistence.md's Security section).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class UserSession(UUIDPKMixin, TimestampMixin, Base):
    """One user's workspace. Every other session-scoped table (analyses,
    products, routines, chats, comparisons) still keys off this table's
    id, unchanged -- only this table itself gained an owner.
    """

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
