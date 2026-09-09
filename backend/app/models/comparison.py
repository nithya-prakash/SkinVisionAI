"""Optional persisted record of a Phase 5 stateless product comparison.

``POST /api/products/compare`` remains stateless by default (Phase 5's
documented design, see docs/routine.md) -- a row here is created only
when the caller opts in via ``ProductCompareRequest.persist=True``
(Phase 8). Mirrors ``Product.analysis_result``'s existing
request-plus-result JSON pattern.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ComparisonRecord(UUIDPKMixin, TimestampMixin, Base):
    """One persisted ``ProductCompareRequest`` + its ``ProductComparisonResult``."""

    __tablename__ = "comparison_records"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
