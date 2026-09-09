"""Skin analysis run — visual observations only, never a diagnosis."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class SkinAnalysis(UUIDPKMixin, TimestampMixin, Base):
    """A single analysis run tying an image to its structured, non-diagnostic
    visual observations. Populated starting in Phase 3 (vision pipeline).
    """

    __tablename__ = "skin_analyses"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("image_metadata.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    visual_observations: Mapped[list] = mapped_column(JSON, nullable=True)
    structured_response: Mapped[dict] = mapped_column(JSON, nullable=True)
