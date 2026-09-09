"""Public request/response contract for the agent chat endpoint, and the
LLM's structured final-answer output schema.

``AgentFinalAnswerLLMOutput`` is the raw shape the model must fill in via
the "provide_final_answer" tool (see ``app.llm.provider``). Like Phase
6's ``ExplanationLLMOutput``, it deliberately has no ``severity``,
``source``, ``interactions``, or numeric-score field -- the model has no
field to invent or alter a domain fact into. Anything precise the user
sees (an exact severity, a citation, a rule_id) comes from
``AgentResponse.tool_trace`` / ``citations``, assembled by the backend
from actual tool results, never from the model's free text.
"""
from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.trace import ToolCallTraceEntry
from app.schemas.common import DISCLAIMER


class AgentFinalAnswerLLMOutput(BaseModel):
    """What the model returns when it calls "provide_final_answer"."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=2000)
    key_points: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=6)


class ChatLink(BaseModel):
    """Optional trusted-context reference (Phase 8), set only when a new
    chat session is being created about an existing, already-computed
    result. Exactly one field must be set -- a chat is "about" one thing
    at a time. When present, the agent loop injects that row's persisted
    JSON result as if a tool had already returned it (see
    ``app.services.agent_service`` and docs/agent.md); the row must
    already exist (validated by the service layer, not here, since this
    schema has no database access) and its id must have been returned by
    a prior request -- a client can never fabricate the linked content
    itself, only point at something the backend already computed.
    """

    model_config = ConfigDict(extra="forbid")

    skin_analysis_id: UUID | None = None
    product_id: UUID | None = None
    routine_analysis_id: UUID | None = None
    comparison_id: UUID | None = None

    @model_validator(mode="after")
    def _exactly_one_set(self) -> "ChatLink":
        set_count = sum(
            1
            for value in (
                self.skin_analysis_id,
                self.product_id,
                self.routine_analysis_id,
                self.comparison_id,
            )
            if value is not None
        )
        if set_count != 1:
            raise ValueError(
                "Exactly one of skin_analysis_id, product_id, routine_analysis_id, "
                "comparison_id must be set."
            )
        return self


class AgentChatRequest(BaseModel):
    """Payload for ``POST /api/agent/chat``.

    ``session_id``/``chat_session_id`` are optional, matching every other
    session-scoped endpoint's convention (e.g.
    ``ProductAnalyzeRequest.session_id``): omit both for a fresh anonymous
    session and a fresh chat; pass ``chat_session_id`` to continue an
    existing conversation (its prior turns are loaded server-side as
    request-scoped context for this turn only -- see docs/agent.md's
    "conversational memory" section for why this stays deliberately
    small, no embeddings/vector memory/user profiling).

    ``context`` is optional, client-supplied, plain-data hinting (e.g.
    product names currently on screen) -- like ``message``, it is
    untrusted input, never treated as an authoritative skincare fact. Any
    ingredient/product fact the agent's answer relies on must come from an
    actual tool call, not from here.

    ``link`` (Phase 8) is only applied when this request creates a *new*
    chat session (i.e. ``chat_session_id`` was omitted or unknown) -- it
    is ignored when continuing an existing one, whose linkage (if any)
    was already fixed at creation.
    """

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None
    chat_session_id: UUID | None = None
    context: dict[str, object] | None = None
    link: ChatLink | None = None


class Citation(BaseModel):
    """One source, deduplicated from the tool trace -- never supplied or
    altered by the LLM.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_url: str | None = None


class AgentStatus(StrEnum):
    """How the agent turn concluded."""

    SUCCESS = "success"
    TOOL_ERROR = "tool_error"
    LLM_UNAVAILABLE = "llm_unavailable"
    VALIDATION_ERROR = "validation_error"
    MAX_TOOL_CALLS = "max_tool_calls"


class AgentResponse(BaseModel):
    """Response for ``POST /api/agent/chat``.

    Never carries a raw provider object, a system prompt, an API key, or
    hidden reasoning -- only the final answer text, the safe structured
    tool trace, and facts derived from it. See docs/agent.md's security
    section.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str
    tool_trace: list[ToolCallTraceEntry] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    status: AgentStatus
    chat_session_id: UUID | None = None
    message_id: UUID | None = None
