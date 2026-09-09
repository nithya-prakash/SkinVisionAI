"""Chat-history retrieval schemas (Phase 8).

Distinct from ``app.agent.schemas`` (the live ``POST /api/agent/chat``
turn contract, owned by Phase 7) -- this module is read-only history
retrieval: ``GET /api/chat/sessions/{id}`` and
``GET /api/chat/sessions/{id}/messages``. Reuses
``app.agent.trace.ToolCallTraceEntry`` for the per-message trace shape so
a message read back from history looks exactly like the trace already
returned live by ``POST /api/agent/chat`` -- no separate, possibly
drifted shape.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agent.trace import ToolCallTraceEntry


class ChatSessionRead(BaseModel):
    """One ``ChatSession`` row, including its optional linked-context
    reference (at most one of the four is ever expected to be set --
    see ``app.models.chat.ChatSession``).
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    skin_analysis_id: UUID | None = None
    product_id: UUID | None = None
    routine_analysis_id: UUID | None = None
    comparison_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    """One persisted ``ChatMessage``. ``tool_trace`` is populated (from
    ``AgentTrace`` rows) only for assistant messages that called at least
    one tool -- empty for user messages and for assistant messages that
    answered without one. Never carries hidden reasoning: this is exactly
    the same safe trace shape ``POST /api/agent/chat`` already returns
    live.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    chat_session_id: UUID
    role: str
    content: str
    tool_trace: list[ToolCallTraceEntry] = Field(default_factory=list)
    created_at: datetime


class ChatMessagesResponse(BaseModel):
    """Response for ``GET /api/chat/sessions/{id}/messages``."""

    model_config = ConfigDict(extra="forbid")

    chat_session_id: UUID
    messages: list[ChatMessageRead] = Field(default_factory=list)
