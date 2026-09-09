"""Chat-history retrieval endpoints (Phase 8).

Distinct from ``app.api.agent`` (``POST /api/agent/chat``, the live
agent turn, owned by Phase 7) -- this router is read-only: reload a
conversation after a refresh instead of losing it.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.chat import ChatMessagesResponse, ChatSessionRead
from app.services.chat_query_service import (
    ChatSessionNotFoundError,
    get_chat_session,
    list_chat_messages,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions/{chat_session_id}", response_model=ChatSessionRead, status_code=200)
async def get_chat_session_endpoint(
    chat_session_id: UUID, db: AsyncSession = Depends(get_db)
) -> ChatSessionRead:
    """One chat session's metadata, including its optional linked-context
    reference (Phase 8). 404 for an unknown id.
    """
    try:
        return await get_chat_session(db, chat_session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "chat_session_not_found", "message": str(exc)},
        ) from exc


@router.get(
    "/sessions/{chat_session_id}/messages", response_model=ChatMessagesResponse, status_code=200
)
async def list_chat_messages_endpoint(
    chat_session_id: UUID, db: AsyncSession = Depends(get_db)
) -> ChatMessagesResponse:
    """Every message in a chat session, chronological, each assistant
    message's tool trace included -- exactly the same safe shape
    ``POST /api/agent/chat`` already returns live. 404 for an unknown id.
    """
    try:
        messages = await list_chat_messages(db, chat_session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "chat_session_not_found", "message": str(exc)},
        ) from exc
    return ChatMessagesResponse(chat_session_id=chat_session_id, messages=messages)
