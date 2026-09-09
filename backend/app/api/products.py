"""Product endpoints.

Phase 4: single-product ingredient analysis (``POST /api/products/analyze``,
persisted). Phase 5: stateless product-vs-product comparison
(``POST /api/products/compare``, not persisted -- see docs/routine.md).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.products.comparator import compare_products
from app.schemas.product import (
    ProductAnalyzeRequest,
    ProductAnalyzeResponse,
    ProductCompareRequest,
    ProductComparisonResult,
)
from app.services.ingredient_service import analyze_product
from app.services.persistence_service import persist_comparison

router = APIRouter(prefix="/api/products", tags=["products"])


@router.post("/analyze", response_model=ProductAnalyzeResponse, status_code=201)
async def analyze_product_endpoint(
    payload: ProductAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
) -> ProductAnalyzeResponse:
    """Parse and normalize a product's raw ingredient list and run the
    deterministic compatibility engine over it. No LLM call, no network
    call -- purely deterministic rule lookups against the versioned rule
    set. Always returns 201; unknown ingredients and an absent rule for a
    given pair are normal, informative results, not errors.
    """
    return await analyze_product(
        db=db,
        session_id=str(payload.session_id) if payload.session_id else None,
        name=payload.name,
        category=payload.category,
        raw_ingredient_text=payload.raw_ingredient_text,
    )


@router.post("/compare", response_model=ProductComparisonResult, status_code=200)
async def compare_products_endpoint(
    payload: ProductCompareRequest,
    db: AsyncSession = Depends(get_db),
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
        record = await persist_comparison(db, payload, result)
        result = result.model_copy(update={"id": record.id})
    return result
