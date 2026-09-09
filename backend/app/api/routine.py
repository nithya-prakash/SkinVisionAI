"""Routine endpoints (Phase 5: stateless routine analysis).

Persisted AM/PM routine CRUD (``POST /api/routine``, from the Phase 1
schema) is not implemented yet -- this router covers only
``POST /api/routine/analyze``, which is stateless by default and writes
nothing to the database. See docs/routine.md for why. Phase 8 adds an
opt-in ``persist=True`` request field (see docs/persistence.md); the
default (``False``) behavior is byte-identical to Phase 5.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routine.analyzer import analyze_routine
from app.schemas.routine import RoutineAnalysisRequest, RoutineAnalysisResult
from app.services.persistence_service import persist_routine_analysis

router = APIRouter(prefix="/api/routine", tags=["routine"])


@router.post("/analyze", response_model=RoutineAnalysisResult, status_code=200)
async def analyze_routine_endpoint(
    payload: RoutineAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> RoutineAnalysisResult:
    """Analyze a set of products as a routine: normalized ingredients,
    overlapping actives, cross-product compatibility, and a suggested
    AM/PM ordering. No LLM call, no network call, fully deterministic.

    Stateless by default -- nothing is persisted and ``result.id`` is
    ``None``. Set ``persist: true`` to additionally save the request and
    result as a ``RoutineAnalysisRecord`` and get back its id.
    """
    result = analyze_routine(payload)
    if payload.persist:
        record = await persist_routine_analysis(db, payload, result)
        result = result.model_copy(update={"id": record.id})
    return result
