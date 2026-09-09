"""Opt-in persistence for the Phase 5 stateless routine-analysis and
product-comparison endpoints (Phase 8).

Called only when the request explicitly sets ``persist=True`` --
otherwise these endpoints remain exactly as stateless as Phase 5 designed
them. Mirrors ``Product.analysis_result``'s existing request-plus-result
JSON pattern (``app.services.ingredient_service``) rather than
normalizing either result's internal structure into new columns.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comparison import ComparisonRecord
from app.models.routine_analysis import RoutineAnalysisRecord
from app.schemas.product import ProductCompareRequest, ProductComparisonResult
from app.schemas.routine import RoutineAnalysisRequest, RoutineAnalysisResult
from app.services.session_service import get_or_create_session


async def persist_routine_analysis(
    db: AsyncSession, request: RoutineAnalysisRequest, result: RoutineAnalysisResult
) -> RoutineAnalysisRecord:
    session = await get_or_create_session(
        db, str(request.session_id) if request.session_id else None
    )
    record = RoutineAnalysisRecord(
        session_id=session.id,
        request=request.model_dump(mode="json", exclude={"persist"}),
        result=result.model_dump(mode="json", exclude={"id"}),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def persist_comparison(
    db: AsyncSession, request: ProductCompareRequest, result: ProductComparisonResult
) -> ComparisonRecord:
    session = await get_or_create_session(
        db, str(request.session_id) if request.session_id else None
    )
    record = ComparisonRecord(
        session_id=session.id,
        request=request.model_dump(mode="json", exclude={"persist"}),
        result=result.model_dump(mode="json", exclude={"id"}),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
