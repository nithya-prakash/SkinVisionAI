"""Chat-history retrieval endpoints (Phase 8).

Distinct from ``app.api.agent`` (``POST /api/agent/chat``, the live
agent turn, owned by Phase 7) -- this router is read-only: reload a
conversation after a refresh instead of losing it. Release-hardening
follow-up: both routes require authentication; a ``chat_session_id``
that exists but belongs to a different user is a 403.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.chat import ChatMessagesResponse, ChatSessionRead
from app.services.auth_service import get_current_user
from app.services.chat_query_service import (
    ChatSessionNotFoundError,
    get_chat_session,
    list_chat_messages,
)
from app.services.session_service import SessionOwnershipError, assert_session_owned

router = APIRouter(prefix="/api/chat", tags=["chat"])


async def _owned_chat_session(
    db: AsyncSession, chat_session_id: UUID, current_user: User
) -> ChatSessionRead:
    try:
        chat_session = await get_chat_session(db, chat_session_id)
    except ChatSessionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "chat_session_not_found", "message": str(exc)},
        ) from exc
    try:
        await assert_session_owned(db, chat_session.session_id, current_user)
    except SessionOwnershipError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "chat_session_forbidden",
                "message": f"Chat session {chat_session_id} does not belong to the authenticated user.",
            },
        ) from exc
    return chat_session


@router.get("/sessions/{chat_session_id}", response_model=ChatSessionRead, status_code=200)
async def get_chat_session_endpoint(
    chat_session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSessionRead:
    """One chat session's metadata, including its optional linked-context
    reference (Phase 8). 404 for an unknown id, 403 for someone else's.
    """
    return await _owned_chat_session(db, chat_session_id, current_user)


@router.get(
    "/sessions/{chat_session_id}/messages", response_model=ChatMessagesResponse, status_code=200
)
async def list_chat_messages_endpoint(
    chat_session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatMessagesResponse:
    """Every message in a chat session, chronological, each assistant
    message's tool trace included -- exactly the same safe shape
    ``POST /api/agent/chat`` already returns live. 404 for an unknown id,
    403 for someone else's.
    """
    await _owned_chat_session(db, chat_session_id, current_user)
    messages = await list_chat_messages(db, chat_session_id)
    return ChatMessagesResponse(chat_session_id=chat_session_id, messages=messages)
