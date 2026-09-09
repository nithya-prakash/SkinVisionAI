"""Application-session retrieval schemas (Phase 8; Phase 9 adds the
product/routine/comparison list endpoints History needed).

``SessionRead`` (id + created_at) already existed since Phase 1 in
``app.schemas.analysis`` -- reused here, not duplicated. This module adds
the summary shapes for "what has this session done," used by
``GET /api/sessions/{id}/{analyses,chats,products,routine-analyses,comparisons}``.
Each summary is deliberately small (an id + a few display fields + a
timestamp), not the full nested result -- callers that want the full
detail follow up with the corresponding detail endpoint
(``GET /api/analysis/{id}``, ``GET /api/chat/sessions/{id}/messages``, or
``POST /api/products/analyze`` /``.../compare``/``/api/routine/analyze``
re-run, since Phase 5/6's analysis endpoints are pure functions of their
input and Phase 8 only persists a JSON snapshot, not a re-fetchable
"full" detail endpoint of its own -- see docs/persistence.md).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import AnalysisClientStatus, SessionRead

__all__ = [
    "SessionRead",
    "SessionAnalysisSummary",
    "SessionAnalysesResponse",
    "SessionChatSummary",
    "SessionChatsResponse",
    "SessionProductSummary",
    "SessionProductsResponse",
    "SessionRoutineAnalysisSummary",
    "SessionRoutineAnalysesResponse",
    "SessionComparisonSummary",
    "SessionComparisonsResponse",
]


class SessionAnalysisSummary(BaseModel):
    """One ``SkinAnalysis`` row, summarized for a session's analysis list."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: AnalysisClientStatus
    created_at: datetime


class SessionAnalysesResponse(BaseModel):
    """Response for ``GET /api/sessions/{id}/analyses``."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    analyses: list[SessionAnalysisSummary] = Field(default_factory=list)


class SessionChatSummary(BaseModel):
    """One ``ChatSession`` row, summarized for a session's chat list."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class SessionChatsResponse(BaseModel):
    """Response for ``GET /api/sessions/{id}/chats``."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    chats: list[SessionChatSummary] = Field(default_factory=list)


class SessionProductSummary(BaseModel):
    """One ``Product`` row (Phase 4 single-product analysis), summarized."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    category: str | None = None
    interaction_count: int = Field(ge=0)
    unknown_ingredient_count: int = Field(ge=0)
    created_at: datetime


class SessionProductsResponse(BaseModel):
    """Response for ``GET /api/sessions/{id}/products``."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    products: list[SessionProductSummary] = Field(default_factory=list)


class SessionRoutineAnalysisSummary(BaseModel):
    """One ``RoutineAnalysisRecord`` row (Phase 8 opt-in persisted routine
    analysis), summarized. Only records saved with ``persist: true`` ever
    appear here -- see docs/persistence.md.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    product_count: int = Field(ge=0)
    interaction_count: int = Field(ge=0)
    created_at: datetime


class SessionRoutineAnalysesResponse(BaseModel):
    """Response for ``GET /api/sessions/{id}/routine-analyses``."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    routine_analyses: list[SessionRoutineAnalysisSummary] = Field(default_factory=list)


class SessionComparisonSummary(BaseModel):
    """One ``ComparisonRecord`` row (Phase 8 opt-in persisted product
    comparison), summarized. Only records saved with ``persist: true``
    ever appear here.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    product_a_name: str
    product_b_name: str
    interaction_count: int = Field(ge=0)
    created_at: datetime


class SessionComparisonsResponse(BaseModel):
    """Response for ``GET /api/sessions/{id}/comparisons``."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    comparisons: list[SessionComparisonSummary] = Field(default_factory=list)
