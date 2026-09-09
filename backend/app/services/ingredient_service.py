"""Product ingredient analysis orchestration (Phase 4).

API route -> ingredient_service -> parser -> compatibility engine ->
Pydantic result -> database persistence. Mirrors the Phase 2/3 service
pattern. No LLM, no network call, fully deterministic and offline.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.parser import parse_ingredient_list
from app.models.product import Product
from app.schemas.common import ProductCategory
from app.schemas.product import ProductAnalyzeResponse
from app.services.session_service import get_or_create_session

logger = logging.getLogger(__name__)


async def analyze_product(
    *,
    db: AsyncSession,
    session_id: str | None,
    name: str,
    category: ProductCategory | None,
    raw_ingredient_text: str,
) -> ProductAnalyzeResponse:
    """Parse, normalize, and run the compatibility engine over one
    product's raw ingredient text, then persist and return the result.
    """
    tokens = parse_ingredient_list(raw_ingredient_text)
    result = check_ingredient_compatibility(tokens)

    session = await get_or_create_session(db, session_id)

    product_row = Product(
        session_id=session.id,
        name=name,
        category=category.value if category else None,
        raw_ingredient_text=raw_ingredient_text,
        normalized_ingredients=[ing.model_dump(mode="json") for ing in result.ingredients],
        analysis_result=result.model_dump(mode="json"),
    )
    db.add(product_row)
    await db.commit()
    await db.refresh(product_row)

    logger.info(
        "product_analyzed product_id=%s session_id=%s ingredient_count=%s "
        "unknown_count=%s interaction_count=%s",
        product_row.id,
        session.id,
        len(result.ingredients),
        len(result.unknown_ingredients),
        len(result.interactions),
    )

    return ProductAnalyzeResponse(
        product_id=product_row.id,
        session_id=session.id,
        name=product_row.name,
        category=category,
        compatibility=result,
    )
