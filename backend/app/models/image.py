"""Image metadata — never stores raw image bytes or logs image content."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ImageMetadata(UUIDPKMixin, TimestampMixin, Base):
    """Metadata about an uploaded image. The image bytes live on disk under
    a retention policy (``Settings.image_retention_mode``); only their
    location and derived, non-sensitive metadata are persisted here.
    ``storage_path`` is null when retention mode is "none" -- the image was
    analyzed in memory and never written to disk.
    """

    __tablename__ = "image_metadata"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_result: Mapped[dict] = mapped_column(JSON, nullable=True)
