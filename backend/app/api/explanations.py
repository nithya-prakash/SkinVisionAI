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
useful even when the LLM is unavailable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.llm.base import LLMProvider
from app.llm.provider import get_llm_provider
from app.schemas.explanation import (
    ComparisonExplanationResponse,
    ProductExplanationResponse,
    RoutineExplanationResponse,
)
from app.schemas.product import ProductAnalyzeRequest, ProductCompareRequest
from app.schemas.routine import RoutineAnalysisRequest
from app.services.explanation_service import explain_comparison, explain_product, explain_routine

router = APIRouter(prefix="/api/explanations", tags=["explanations"])


def _provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


@router.post("/product", response_model=ProductExplanationResponse, status_code=200)
async def explain_product_endpoint(
    payload: ProductAnalyzeRequest,
    provider: LLMProvider = Depends(_provider),
) -> ProductExplanationResponse:
    """Re-runs single-product ingredient analysis and explains it."""
    return await explain_product(payload, provider)


@router.post("/compare", response_model=ComparisonExplanationResponse, status_code=200)
async def explain_comparison_endpoint(
    payload: ProductCompareRequest,
    provider: LLMProvider = Depends(_provider),
    db: AsyncSession = Depends(get_db),
) -> ComparisonExplanationResponse:
    """Re-runs product-vs-product comparison and explains it. Set
    ``persist: true`` (Phase 8) to also save it as a ``ComparisonRecord``
    and get back its id in ``analysis.id``.
    """
    return await explain_comparison(payload, provider, db)


@router.post("/routine", response_model=RoutineExplanationResponse, status_code=200)
async def explain_routine_endpoint(
    payload: RoutineAnalysisRequest,
    provider: LLMProvider = Depends(_provider),
    db: AsyncSession = Depends(get_db),
) -> RoutineExplanationResponse:
    """Re-runs routine analysis and explains it. Set ``persist: true``
    (Phase 8) to also save it as a ``RoutineAnalysisRecord`` and get back
    its id in ``analysis.id``.
    """
    return await explain_routine(payload, provider, db)
