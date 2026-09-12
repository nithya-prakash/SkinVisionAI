"""Product endpoints.

Phase 4: single-product ingredient analysis (``POST /api/products/analyze``,
persisted). Phase 5: stateless product-vs-product comparison
(``POST /api/products/compare``, not persisted -- see docs/routine.md).
Release-hardening follow-up: both require authentication; a client-
supplied ``session_id`` that isn't the caller's own is a 403.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.products.comparator import compare_products
from app.schemas.product import (
    ProductAnalyzeRequest,
    ProductAnalyzeResponse,
    ProductCompareRequest,
    ProductComparisonResult,
)
from app.services.auth_service import get_current_user
from app.services.ingredient_service import analyze_product
from app.services.persistence_service import persist_comparison
from app.services.session_service import SessionOwnershipError, get_or_create_session_for_user

router = APIRouter(prefix="/api/products", tags=["products"])


def _resolve_session_or_403(exc: SessionOwnershipError) -> HTTPException:
    return HTTPException(
        status_code=403, detail={"code": "session_forbidden", "message": str(exc)}
    )


@router.post("/analyze", response_model=ProductAnalyzeResponse, status_code=201)
async def analyze_product_endpoint(
    payload: ProductAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductAnalyzeResponse:
    """Parse and normalize a product's raw ingredient list and run the
    deterministic compatibility engine over it. No LLM call, no network
    call -- purely deterministic rule lookups against the versioned rule
    set. Always returns 201; unknown ingredients and an absent rule for a
    given pair are normal, informative results, not errors.
    """
    try:
        session = await get_or_create_session_for_user(
            db, current_user, str(payload.session_id) if payload.session_id else None
        )
    except SessionOwnershipError as exc:
        raise _resolve_session_or_403(exc) from exc

    return await analyze_product(
        db=db,
        session_id=str(session.id),
        name=payload.name,
        category=payload.category,
        raw_ingredient_text=payload.raw_ingredient_text,
    )


@router.post("/compare", response_model=ProductComparisonResult, status_code=200)
async def compare_products_endpoint(
    payload: ProductCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductComparisonResult:
    """Deterministically compare two products' ingredients: shared/unique
    ingredients, shared active categories, and any compatibility
    interactions between them. No LLM call, no network call. Never
    computes an overall "better product" verdict.

    Stateless by default -- nothing is persisted and ``result.id`` is
    ``None``. Set ``persist: true`` to additionally save the request and
    result as a ``ComparisonRecord`` and get back its id.
    """
    result = compare_products(payload)
    if payload.persist:
        try:
            session = await get_or_create_session_for_user(
                db, current_user, str(payload.session_id) if payload.session_id else None
            )
        except SessionOwnershipError as exc:
            raise _resolve_session_or_403(exc) from exc
        record = await persist_comparison(db, session, payload, result)
        result = result.model_copy(update={"id": record.id})
    return result
