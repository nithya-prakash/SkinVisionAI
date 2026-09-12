"""Shared session resolution and read-only session retrieval (Phase 8,
extended Phase 9): "what has this session done" for
``GET /api/sessions/{id}/{analyses,chats,products,routine-analyses,comparisons}``.

``get_or_create_session`` (Phase 1) is a low-level, ownership-agnostic
utility -- resolve-or-create by raw id -- kept for internal/test use.
Every API route now goes through ``get_or_create_session_for_user``
instead (release-hardening follow-up): a ``UserSession`` is owned by a
``User``, so a bare UUID is no longer sufficient to reach it. See
docs/persistence.md's Security section.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession
from app.models.analysis import SkinAnalysis
from app.models.comparison import ComparisonRecord
from app.models.image import ImageMetadata
from app.models.product import Product
from app.models.routine_analysis import RoutineAnalysisRecord
from app.models.session import UserSession
from app.models.user import User
from app.schemas.session import (
    SessionAnalysisSummary,
    SessionChatSummary,
    SessionComparisonSummary,
    SessionProductSummary,
    SessionRoutineAnalysisSummary,
)
from app.services.analysis_query_service import derive_client_status


class SessionOwnershipError(Exception):
    """Raised when a client-supplied ``session_id`` names a session that
    exists but belongs to a different user. The API layer turns this into
    a 403 -- never a silent fallback to the caller's own session, which
    would mask exactly the kind of probing/mistake this is meant to catch.
    """


async def get_or_create_session(db: AsyncSession, session_id: str | None) -> UserSession:
    """Reuse an existing session if a valid, known id was given.

    Pre-auth, "otherwise create a new one" meant a bare anonymous
    session. Since ``UserSession.user_id`` is now required (release-
    hardening follow-up), that fallback creates a throwaway ``User`` for
    it -- fine for what this fallback is actually used for today (a
    handful of service-layer tests that call ``ingest_image``/
    ``analyze_product`` directly with ``session_id=None``, bypassing the
    API layer entirely), but **not** the authenticated path: every real
    route resolves a session via ``get_or_create_session_for_user``
    instead, which never hits this branch. Full session-lifecycle
    semantics (expiry, rotation) remain out of scope for this project.
    """
    if session_id:
        try:
            parsed = uuid.UUID(session_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            existing = await db.get(UserSession, parsed)
            if existing is not None:
                return existing

    throwaway_user = User(
        email=f"anonymous-{uuid.uuid4().hex}@example.invalid",
        hashed_password="unusable",
    )
    db.add(throwaway_user)
    await db.flush()

    session = UserSession(user_id=throwaway_user.id)
    db.add(session)
    await db.flush()
    return session


async def get_or_create_session_for_user(
    db: AsyncSession, user: User, session_id: str | None
) -> UserSession:
    """Resolve the authenticated user's own session -- the fix for
    "anonymous session ID alone grants access." A user has exactly one
    session (``UserSession.user_id`` is unique), created lazily here the
    first time it's needed (normally at registration; see
    ``auth_service.register_user``, which calls this immediately).

    If ``session_id`` is given and names a session that exists but is
    owned by someone else, raises ``SessionOwnershipError`` rather than
    silently falling back -- a UUID is no longer sufficient on its own,
    it must also belong to the authenticated caller. An unknown/invalid
    id (never existed, or malformed) falls back to the caller's own
    session, same as the pre-auth ``get_or_create_session`` behavior for
    a not-found id -- that's a no-op fallback, not a security concern.
    """
    if session_id:
        try:
            parsed = uuid.UUID(session_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            existing = await db.get(UserSession, parsed)
            if existing is not None:
                if existing.user_id != user.id:
                    raise SessionOwnershipError(
                        f"session {parsed} does not belong to the authenticated user"
                    )
                return existing

    result = await db.execute(select(UserSession).where(UserSession.user_id == user.id))
    own_session = result.scalar_one_or_none()
    if own_session is not None:
        return own_session

    session = UserSession(user_id=user.id)
    db.add(session)
    await db.flush()
    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> UserSession | None:
    """Look up a session by id. Returns ``None`` for an unknown id --
    callers (the API layer) turn that into a 404 rather than silently
    creating a new, unrelated session, per this endpoint's read-only
    contract (unlike ``get_or_create_session``, used only by write paths).
    """
    return await db.get(UserSession, session_id)


async def assert_session_owned(db: AsyncSession, resource_session_id: uuid.UUID, user: User) -> None:
    """Reusable ownership check for any by-id resource route (an
    analysis, a chat session, a persisted routine/comparison record): the
    route's own service call already fetches the resource (and 404s if it
    doesn't exist) -- this asserts the resource's own ``session_id``
    belongs to the authenticated caller. Raises ``SessionOwnershipError``
    (the API layer turns that into a 403) on any mismatch, including a
    dangling/unknown session id, which should never happen for a resource
    that was just successfully fetched but is treated as "not yours"
    rather than crashing either way.
    """
    session = await db.get(UserSession, resource_session_id)
    if session is None or session.user_id != user.id:
        raise SessionOwnershipError(
            f"resource under session {resource_session_id} does not belong to the authenticated user"
        )


async def list_session_analyses(
    db: AsyncSession, session_id: uuid.UUID
) -> list[SessionAnalysisSummary]:
    """This session's ``SkinAnalysis`` rows, newest first, each summarized
    with its derived client-facing status (see
    ``app.services.analysis_query_service.derive_client_status``).
    """
    stmt = (
        select(SkinAnalysis, ImageMetadata)
        .join(ImageMetadata, ImageMetadata.id == SkinAnalysis.image_id)
        .where(SkinAnalysis.session_id == session_id)
        .order_by(SkinAnalysis.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        SessionAnalysisSummary(
            id=analysis.id,
            status=derive_client_status(analysis, image),
            created_at=analysis.created_at,
        )
        for analysis, image in rows
    ]


async def list_session_chats(db: AsyncSession, session_id: uuid.UUID) -> list[SessionChatSummary]:
    """This session's ``ChatSession`` rows, newest first, each with its
    message count (a single grouped query, not N+1).
    """
    stmt = (
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.chat_session_id == ChatSession.id)
        .where(ChatSession.session_id == session_id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        SessionChatSummary(
            id=chat_session.id,
            message_count=message_count,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
        )
        for chat_session, message_count in rows
    ]


async def list_session_products(
    db: AsyncSession, session_id: uuid.UUID
) -> list[SessionProductSummary]:
    """This session's ``Product`` rows (Phase 4 single-product ingredient
    analysis), newest first. Counts are derived at query time from the
    already-persisted ``analysis_result`` JSON -- no new column, no
    recomputation of the deterministic engine.
    """
    stmt = (
        select(Product)
        .where(Product.session_id == session_id)
        .order_by(Product.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    summaries: list[SessionProductSummary] = []
    for product in rows:
        result = product.analysis_result or {}
        summaries.append(
            SessionProductSummary(
                id=product.id,
                name=product.name,
                category=product.category,
                interaction_count=len(result.get("interactions", [])),
                unknown_ingredient_count=len(result.get("unknown_ingredients", [])),
                created_at=product.created_at,
            )
        )
    return summaries


async def list_session_routine_analyses(
    db: AsyncSession, session_id: uuid.UUID
) -> list[SessionRoutineAnalysisSummary]:
    """This session's opt-in-persisted ``RoutineAnalysisRecord`` rows
    (Phase 8), newest first. Only routine analyses saved with
    ``persist: true`` appear here.
    """
    stmt = (
        select(RoutineAnalysisRecord)
        .where(RoutineAnalysisRecord.session_id == session_id)
        .order_by(RoutineAnalysisRecord.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    summaries: list[SessionRoutineAnalysisSummary] = []
    for record in rows:
        result = record.result or {}
        summaries.append(
            SessionRoutineAnalysisSummary(
                id=record.id,
                product_count=len(result.get("products", [])),
                interaction_count=len(result.get("interactions", [])),
                created_at=record.created_at,
            )
        )
    return summaries


async def list_session_comparisons(
    db: AsyncSession, session_id: uuid.UUID
) -> list[SessionComparisonSummary]:
    """This session's opt-in-persisted ``ComparisonRecord`` rows (Phase
    8), newest first. Only comparisons saved with ``persist: true``
    appear here.
    """
    stmt = (
        select(ComparisonRecord)
        .where(ComparisonRecord.session_id == session_id)
        .order_by(ComparisonRecord.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    summaries: list[SessionComparisonSummary] = []
    for record in rows:
        result = record.result or {}
        summaries.append(
            SessionComparisonSummary(
                id=record.id,
                product_a_name=result.get("product_a_name", ""),
                product_b_name=result.get("product_b_name", ""),
                interaction_count=len(result.get("interactions", [])),
                created_at=record.created_at,
            )
        )
    return summaries
