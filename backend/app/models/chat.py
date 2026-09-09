"""Copilot chat sessions/messages and the agent's persisted tool-call trace."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ChatSession(UUIDPKMixin, TimestampMixin, Base):
    """A copilot chat conversation belonging to an anonymous session.

    The four linkage columns (Phase 8) are optional trusted-context
    references: when set, the agent loop injects that row's
    already-computed, already-validated result as if a tool had already
    returned it -- never raw untrusted text, and never bypassing
    ``app.agent.validation``. At most this app expects one to be set per
    chat session (a chat is "about" one thing at a time), but nothing
    enforces that at the database level; the service layer decides which
    one (if any) to populate when a chat session is created. All four are
    ``ON DELETE SET NULL`` -- deleting a referenced analysis must never
    cascade-delete a conversation, it just stops being "about" it.
    """

    __tablename__ = "chat_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skin_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skin_analyses.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    routine_analysis_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routine_analysis_records.id", ondelete="SET NULL"), nullable=True
    )
    comparison_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comparison_records.id", ondelete="SET NULL"), nullable=True
    )


class ChatMessage(UUIDPKMixin, TimestampMixin, Base):
    """A single message (user or assistant) within a chat session."""

    __tablename__ = "chat_messages"

    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_response: Mapped[dict] = mapped_column(JSON, nullable=True)


class AgentTrace(UUIDPKMixin, TimestampMixin, Base):
    """The ordered tool-call trace behind one assistant message, so
    "how this analysis was produced" is reconstructable rather than re-generated.
    """

    __tablename__ = "agent_traces"

    chat_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tool_output: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
