"""User-defined AM/PM skincare routines."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Routine(UUIDPKMixin, TimestampMixin, Base):
    """A named routine (e.g. the user's current AM/PM setup) for a session."""

    __tablename__ = "routines"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="My Routine")


class RoutineItem(UUIDPKMixin, TimestampMixin, Base):
    """A single product placed at a position within a routine's AM or PM sequence."""

    __tablename__ = "routine_items"

    routine_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    time_of_day: Mapped[str] = mapped_column(String(8), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
