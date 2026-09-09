"""Shared anonymous-session resolution (Phase 1) and read-only session
retrieval (Phase 8, extended Phase 9): "what has this session done" for
``GET /api/sessions/{id}/{analyses,chats,products,routine-analyses,comparisons}``.
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
from app.schemas.session import (
    SessionAnalysisSummary,
    SessionChatSummary,
    SessionComparisonSummary,
    SessionProductSummary,
    SessionRoutineAnalysisSummary,
)
from app.services.analysis_query_service import derive_client_status


async def get_or_create_session(db: AsyncSession, session_id: str | None) -> UserSession:
    """Reuse an existing anonymous session if a valid, known id was given;
    otherwise create a new one. Full session-lifecycle semantics (expiry,
    rotation) are out of scope for this project.
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

    session = UserSession()
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
