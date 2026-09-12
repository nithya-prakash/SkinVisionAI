"""Service-layer tests for app.services.ingredient_service.analyze_product.

Uses the real database (see conftest.py), consistent with this project's
convention of verifying database-touching code against real infra.
"""
from __future__ import annotations

import pytest

from app.database import AsyncSessionLocal
from app.models.product import Product
from app.schemas.common import ProductCategory
from app.services.ingredient_service import analyze_product
from tests.helpers.auth import make_user_and_session


@pytest.mark.asyncio
async def test_analyze_product_persists_result() -> None:
    async with AsyncSessionLocal() as db:
        response = await analyze_product(
            db=db,
            session_id=None,
            name="Gentle Hydrating Serum",
            category=ProductCategory.SERUM,
            raw_ingredient_text="Water, Niacinamide, Glycerin, Panthenol",
        )

    assert response.compatibility.interactions == []
    assert len(response.compatibility.ingredients) == 4

    async with AsyncSessionLocal() as db:
        row = await db.get(Product, response.product_id)

    assert row is not None
    assert row.name == "Gentle Hydrating Serum"
    assert row.category == "serum"
    assert row.raw_ingredient_text == "Water, Niacinamide, Glycerin, Panthenol"
    assert len(row.normalized_ingredients) == 4
    assert row.analysis_result is not None
    assert row.analysis_result["disclaimer"].startswith("SkinVision AI provides educational")


@pytest.mark.asyncio
async def test_analyze_product_persists_interactions_when_present() -> None:
    async with AsyncSessionLocal() as db:
        response = await analyze_product(
            db=db,
            session_id=None,
            name="Retinol + Acid Treatment",
            category=None,
            raw_ingredient_text="Retinol, Glycolic Acid",
        )

        row = await db.get(Product, response.product_id)

    assert len(response.compatibility.interactions) == 1
    assert len(row.analysis_result["interactions"]) == 1
    assert row.analysis_result["interactions"][0]["severity"] == "caution"


@pytest.mark.asyncio
async def test_analyze_product_reuses_existing_session() -> None:
    async with AsyncSessionLocal() as db:
        _, existing = await make_user_and_session(db)
        await db.commit()
        existing_id = existing.id

    async with AsyncSessionLocal() as db:
        response = await analyze_product(
            db=db,
            session_id=str(existing_id),
            name="Test Product",
            category=None,
            raw_ingredient_text="Water",
        )

    assert response.session_id == existing_id


@pytest.mark.asyncio
async def test_analyze_product_with_unknown_ingredients() -> None:
    async with AsyncSessionLocal() as db:
        response = await analyze_product(
            db=db,
            session_id=None,
            name="Mystery Serum",
            category=None,
            raw_ingredient_text="Water, NovelComplexXYZ",
        )

    assert "NovelComplexXYZ" in response.compatibility.unknown_ingredients
