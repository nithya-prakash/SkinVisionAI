"""Session endpoints (Phase 8; Phase 9 adds products/routine-analyses/comparisons).

Lets a client explicitly create an application session and later
reconstruct "what has this session done" after a page refresh -- the
session id itself is a plain, non-secret UUID (see docs/persistence.md's
security section for why this needs no auth to be safe, consistent with
every other UUID-addressable resource already in this app).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.analysis import SessionRead
from app.schemas.session import (
    SessionAnalysesResponse,
    SessionChatsResponse,
    SessionComparisonsResponse,
    SessionProductsResponse,
    SessionRoutineAnalysesResponse,
)
from app.services.session_service import (
    get_or_create_session,
    get_session,
    list_session_analyses,
    list_session_chats,
    list_session_comparisons,
    list_session_products,
    list_session_routine_analyses,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=201)
async def create_session(db: AsyncSession = Depends(get_db)) -> SessionRead:
    """Create a new anonymous session explicitly."""
    session = await get_or_create_session(db, None)
    await db.commit()
    await db.refresh(session)
    return SessionRead(id=session.id, created_at=session.created_at)


@router.get("/{session_id}", response_model=SessionRead, status_code=200)
async def get_session_endpoint(session_id: UUID, db: AsyncSession = Depends(get_db)) -> SessionRead:
    """Look up a session by id. 404 for an unknown id -- never silently
    creates a new, unrelated session for a read endpoint that names one.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    return SessionRead(id=session.id, created_at=session.created_at)


@router.get("/{session_id}/analyses", response_model=SessionAnalysesResponse, status_code=200)
async def list_analyses_endpoint(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionAnalysesResponse:
    """This session's skin analyses, newest first. 404 for an unknown
    session id (an empty list would be ambiguous with "unknown session").
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    analyses = await list_session_analyses(db, session_id)
    return SessionAnalysesResponse(session_id=session_id, analyses=analyses)


@router.get("/{session_id}/chats", response_model=SessionChatsResponse, status_code=200)
async def list_chats_endpoint(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionChatsResponse:
    """This session's chat sessions, newest first, each with its message
    count. 404 for an unknown session id.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    chats = await list_session_chats(db, session_id)
    return SessionChatsResponse(session_id=session_id, chats=chats)


@router.get("/{session_id}/products", response_model=SessionProductsResponse, status_code=200)
async def list_products_endpoint(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionProductsResponse:
    """This session's single-product ingredient analyses (Phase 4), newest
    first. 404 for an unknown session id.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    products = await list_session_products(db, session_id)
    return SessionProductsResponse(session_id=session_id, products=products)


@router.get(
    "/{session_id}/routine-analyses", response_model=SessionRoutineAnalysesResponse, status_code=200
)
async def list_routine_analyses_endpoint(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionRoutineAnalysesResponse:
    """This session's opt-in-persisted routine analyses (Phase 8), newest
    first. Only those saved with ``persist: true`` appear here. 404 for
    an unknown session id.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    routine_analyses = await list_session_routine_analyses(db, session_id)
    return SessionRoutineAnalysesResponse(session_id=session_id, routine_analyses=routine_analyses)


@router.get("/{session_id}/comparisons", response_model=SessionComparisonsResponse, status_code=200)
async def list_comparisons_endpoint(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionComparisonsResponse:
    """This session's opt-in-persisted product comparisons (Phase 8),
    newest first. Only those saved with ``persist: true`` appear here.
    404 for an unknown session id.
    """
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": f"No session exists with id {session_id}"},
        )
    comparisons = await list_session_comparisons(db, session_id)
    return SessionComparisonsResponse(session_id=session_id, comparisons=comparisons)
