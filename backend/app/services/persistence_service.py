"""Opt-in persistence for the Phase 5 stateless routine-analysis and
product-comparison endpoints (Phase 8).

Called only when the request explicitly sets ``persist=True`` --
otherwise these endpoints remain exactly as stateless as Phase 5 designed
them. Mirrors ``Product.analysis_result``'s existing request-plus-result
JSON pattern (``app.services.ingredient_service``) rather than
normalizing either result's internal structure into new columns.

Both functions take an already-resolved, already-ownership-checked
``UserSession`` (release-hardening follow-up) rather than deriving one
from ``request.session_id`` internally -- session resolution/ownership
is the API layer's job (``app.services.auth_service``/
``session_service.get_or_create_session_for_user``), done once per
request, not re-derived per service call.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comparison import ComparisonRecord
from app.models.routine_analysis import RoutineAnalysisRecord
from app.models.session import UserSession
from app.schemas.product import ProductCompareRequest, ProductComparisonResult
from app.schemas.routine import RoutineAnalysisRequest, RoutineAnalysisResult


async def persist_routine_analysis(
    db: AsyncSession, session: UserSession, request: RoutineAnalysisRequest, result: RoutineAnalysisResult
) -> RoutineAnalysisRecord:
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
    db: AsyncSession, session: UserSession, request: ProductCompareRequest, result: ProductComparisonResult
) -> ComparisonRecord:
    record = ComparisonRecord(
        session_id=session.id,
        request=request.model_dump(mode="json", exclude={"persist"}),
        result=result.model_dump(mode="json", exclude={"id"}),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
