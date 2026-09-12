"""Explanation endpoints (Phase 6).

Each endpoint accepts the *same* request shape as its Phase 4/5 sibling
deterministic-only endpoint (``/api/products/analyze``,
``/api/products/compare``, ``/api/routine/analyze``) and internally
re-runs that exact deterministic analysis itself -- the frontend can
never submit an "already computed" result to bypass the deterministic
engines. See docs/llm.md.

All three always return 200 with the deterministic ``analysis`` present;
``explanation`` is ``null`` with ``explanation_status="unavailable"``
when the LLM call or anti-hallucination validation fails, rather than
failing the whole request -- the deterministic analysis must remain
useful even when the LLM is unavailable. Release-hardening follow-up:
every endpoint requires authentication (consistent with every other
session-scoped/app endpoint); ``/compare`` and ``/routine`` additionally
resolve/check ownership of ``session_id`` when ``persist: true``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.llm.base import LLMProvider
from app.llm.provider import get_llm_provider
from app.models.session import UserSession
from app.models.user import User
from app.schemas.explanation import (
    ComparisonExplanationResponse,
    ProductExplanationResponse,
    RoutineExplanationResponse,
)
from app.schemas.product import ProductAnalyzeRequest, ProductCompareRequest
from app.schemas.routine import RoutineAnalysisRequest
from app.services.auth_service import get_current_user
from app.services.explanation_service import explain_comparison, explain_product, explain_routine
from app.services.session_service import SessionOwnershipError, get_or_create_session_for_user

router = APIRouter(prefix="/api/explanations", tags=["explanations"])


def _provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


async def _session_for_persist(
    db: AsyncSession, current_user: User, session_id
) -> UserSession | None:
    """Only resolves a session when the request actually needs one
    (``persist: true``) -- the two stateless-by-default endpoints below
    shouldn't pay for a session lookup they don't use.
    """
    try:
        return await get_or_create_session_for_user(
            db, current_user, str(session_id) if session_id else None
        )
    except SessionOwnershipError as exc:
        raise HTTPException(
            status_code=403, detail={"code": "session_forbidden", "message": str(exc)}
        ) from exc


@router.post("/product", response_model=ProductExplanationResponse, status_code=200)
async def explain_product_endpoint(
    payload: ProductAnalyzeRequest,
    provider: LLMProvider = Depends(_provider),
    current_user: User = Depends(get_current_user),
) -> ProductExplanationResponse:
    """Re-runs single-product ingredient analysis and explains it.
    Stateless -- never persists, so no session resolution needed beyond
    requiring the caller be authenticated.
    """
    return await explain_product(payload, provider)


@router.post("/compare", response_model=ComparisonExplanationResponse, status_code=200)
async def explain_comparison_endpoint(
    payload: ProductCompareRequest,
    provider: LLMProvider = Depends(_provider),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ComparisonExplanationResponse:
    """Re-runs product-vs-product comparison and explains it. Set
    ``persist: true`` (Phase 8) to also save it as a ``ComparisonRecord``
    and get back its id in ``analysis.id``.
    """
    session = None
    if payload.persist:
        session = await _session_for_persist(db, current_user, payload.session_id)
    return await explain_comparison(payload, provider, db, session)


@router.post("/routine", response_model=RoutineExplanationResponse, status_code=200)
async def explain_routine_endpoint(
    payload: RoutineAnalysisRequest,
    provider: LLMProvider = Depends(_provider),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutineExplanationResponse:
    """Re-runs routine analysis and explains it. Set ``persist: true``
    (Phase 8) to also save it as a ``RoutineAnalysisRecord`` and get back
    its id in ``analysis.id``.
    """
    session = None
    if payload.persist:
        session = await _session_for_persist(db, current_user, payload.session_id)
    return await explain_routine(payload, provider, db, session)
