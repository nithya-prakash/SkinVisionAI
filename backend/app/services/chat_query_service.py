"""Chat-history retrieval (Phase 8).

Read-only counterpart to ``app.services.agent_service`` (which writes
``ChatSession``/``ChatMessage``/``AgentTrace`` rows while running a live
turn) -- this module only reads them back, reconstructing each assistant
message's tool trace from its ``AgentTrace`` rows in the same shape
``POST /api/agent/chat`` already returns live, so a reloaded conversation
looks identical to one still in memory.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.trace import ToolCallTraceEntry
from app.models.chat import AgentTrace, ChatMessage, ChatSession
from app.schemas.chat import ChatMessageRead, ChatSessionRead


class ChatSessionNotFoundError(Exception):
    """Raised when a requested ``chat_session_id`` does not exist."""


async def get_chat_session(db: AsyncSession, chat_session_id: uuid.UUID) -> ChatSessionRead:
    chat_session = await db.get(ChatSession, chat_session_id)
    if chat_session is None:
        raise ChatSessionNotFoundError(f"No chat session exists with id {chat_session_id}")
    return ChatSessionRead(
        id=chat_session.id,
        session_id=chat_session.session_id,
        skin_analysis_id=chat_session.skin_analysis_id,
        product_id=chat_session.product_id,
        routine_analysis_id=chat_session.routine_analysis_id,
        comparison_id=chat_session.comparison_id,
        created_at=chat_session.created_at,
        updated_at=chat_session.updated_at,
    )


async def list_chat_messages(db: AsyncSession, chat_session_id: uuid.UUID) -> list[ChatMessageRead]:
    """All messages in a chat session, chronological, each assistant
    message's ``tool_trace`` populated from its ``AgentTrace`` rows
    (ordered by ``step_order``). Raises ``ChatSessionNotFoundError`` for
    an unknown id -- an empty message list for a *known* session (e.g.
    one that somehow has no messages yet) is not an error and returns
    ``[]``.
    """
    chat_session = await db.get(ChatSession, chat_session_id)
    if chat_session is None:
        raise ChatSessionNotFoundError(f"No chat session exists with id {chat_session_id}")

    messages = (
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.chat_session_id == chat_session_id)
                .order_by(ChatMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    traces = (
        (
            await db.execute(
                select(AgentTrace)
                .where(AgentTrace.chat_message_id.in_([m.id for m in messages]))
                .order_by(AgentTrace.step_order.asc())
            )
        )
        .scalars()
        .all()
    )
    traces_by_message: dict[uuid.UUID, list[AgentTrace]] = {}
    for trace_row in traces:
        traces_by_message.setdefault(trace_row.chat_message_id, []).append(trace_row)

    return [
        ChatMessageRead(
            id=message.id,
            chat_session_id=message.chat_session_id,
            role=message.role,
            content=message.content,
            tool_trace=[
                ToolCallTraceEntry(
                    tool_name=t.tool_name,
                    arguments=t.tool_input,
                    result=t.tool_output or None,
                    call_index=t.step_order,
                    success=t.success,
                    error=t.error_message,
                )
                for t in traces_by_message.get(message.id, [])
            ],
            created_at=message.created_at,
        )
        for message in messages
    ]
