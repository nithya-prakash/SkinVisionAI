"""Session endpoints (Phase 8; Phase 9 adds products/routine-analyses/
comparisons; release-hardening follow-up adds authentication).

A session is now owned by the authenticated user (``UserSession.user_id``,
unique) rather than reachable by anyone who holds its UUID -- see
docs/persistence.md's Security section. Every route below requires
``Depends(get_current_user)``; a ``session_id`` that exists but belongs to
someone else is a 403, not a silent fallback or a 404 that would leak
whether the id exists.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.analysis import SessionRead
from app.schemas.session import (
    SessionAnalysesResponse,
    SessionChatsResponse,
    SessionComparisonsResponse,
    SessionProductsResponse,
    SessionRoutineAnalysesResponse,
)
from app.services.auth_service import get_current_user
from app.services.session_service import (
    get_or_create_session_for_user,
    get_session,
    list_session_analyses,
    list_session_chats,
    list_session_comparisons,
    list_session_products,
    list_session_routine_analyses,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _forbidden(session_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": "session_forbidden",
            "message": f"Session {session_id} does not belong to the authenticated user.",
        },
    )


async def _owned_session(db: AsyncSession, session_id: UUID, current_user: User):
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    if session.user_id != current_user.id:
        raise _forbidden(session_id)
    return session


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionRead:
    """Return the authenticated user's own session -- idempotent, since a
    user has exactly one (created at registration). Kept as an explicit
    endpoint for the frontend to resolve "what's my session id" on load.
    """
    session = await get_or_create_session_for_user(db, current_user, None)
    await db.commit()
    await db.refresh(session)
    return SessionRead(id=session.id, created_at=session.created_at)


@router.get("/{session_id}", response_model=SessionRead, status_code=200)
async def get_session_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionRead:
    """Look up a session by id. 404 for an unknown id, 403 for one that
    exists but isn't the authenticated user's own.
    """
    session = await _owned_session(db, session_id, current_user)
    return SessionRead(id=session.id, created_at=session.created_at)


@router.get("/{session_id}/analyses", response_model=SessionAnalysesResponse, status_code=200)
async def list_analyses_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionAnalysesResponse:
    """This session's skin analyses, newest first."""
    await _owned_session(db, session_id, current_user)
    analyses = await list_session_analyses(db, session_id)
    return SessionAnalysesResponse(session_id=session_id, analyses=analyses)


@router.get("/{session_id}/chats", response_model=SessionChatsResponse, status_code=200)
async def list_chats_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionChatsResponse:
    """This session's chat sessions, newest first, each with its message
    count.
    """
    await _owned_session(db, session_id, current_user)
    chats = await list_session_chats(db, session_id)
    return SessionChatsResponse(session_id=session_id, chats=chats)


@router.get("/{session_id}/products", response_model=SessionProductsResponse, status_code=200)
async def list_products_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionProductsResponse:
    """This session's single-product ingredient analyses (Phase 4), newest
    first.
    """
    await _owned_session(db, session_id, current_user)
    products = await list_session_products(db, session_id)
    return SessionProductsResponse(session_id=session_id, products=products)


@router.get(
    "/{session_id}/routine-analyses", response_model=SessionRoutineAnalysesResponse, status_code=200
)
async def list_routine_analyses_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionRoutineAnalysesResponse:
    """This session's opt-in-persisted routine analyses (Phase 8), newest
    first. Only those saved with ``persist: true`` appear here.
    """
    await _owned_session(db, session_id, current_user)
    routine_analyses = await list_session_routine_analyses(db, session_id)
    return SessionRoutineAnalysesResponse(session_id=session_id, routine_analyses=routine_analyses)


@router.get("/{session_id}/comparisons", response_model=SessionComparisonsResponse, status_code=200)
async def list_comparisons_endpoint(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionComparisonsResponse:
    """This session's opt-in-persisted product comparisons (Phase 8),
    newest first. Only those saved with ``persist: true`` appear here.
    """
    await _owned_session(db, session_id, current_user)
    comparisons = await list_session_comparisons(db, session_id)
    return SessionComparisonsResponse(session_id=session_id, comparisons=comparisons)
