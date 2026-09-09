"""Optional persisted record of a Phase 5 stateless routine analysis.

``POST /api/routine/analyze`` remains stateless by default (Phase 5's
documented design, see docs/routine.md) -- a row here is created only
when the caller opts in via ``RoutineAnalysisRequest.persist=True``
(Phase 8). Mirrors ``Product.analysis_result``'s existing
request-plus-result JSON pattern rather than normalizing the result's
internal structure into new columns.
"""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class RoutineAnalysisRecord(UUIDPKMixin, TimestampMixin, Base):
    """One persisted ``RoutineAnalysisRequest`` + its ``RoutineAnalysisResult``."""

    __tablename__ = "routine_analysis_records"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
