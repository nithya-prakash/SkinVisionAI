"""Tests for app.schemas.product."""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.common import ProductCategory
from app.schemas.ingredient import NormalizedIngredient
from app.schemas.product import ProductCreate, ProductRead


def test_product_create_valid() -> None:
    product = ProductCreate(
        session_id=uuid4(),
        name="Gentle Hydrating Serum",
        category=ProductCategory.SERUM,
        raw_ingredient_text="Water, Niacinamide, Glycerin, Panthenol",
    )
    assert product.category == ProductCategory.SERUM


def test_product_create_category_and_ingredients_optional() -> None:
    product = ProductCreate(session_id=uuid4(), name="Mystery Cream")
    assert product.category is None
    assert product.raw_ingredient_text is None


def test_product_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(session_id=uuid4(), name="")


def test_product_create_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(session_id=uuid4(), name="Cream", category="miracle_potion")


def test_product_create_missing_required_session_id_raises() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(name="Cream")


def test_product_read_includes_normalized_ingredients() -> None:
    product = ProductRead(
        id=uuid4(),
        session_id=uuid4(),
        name="Gentle Hydrating Serum",
        category=ProductCategory.SERUM,
        normalized_ingredients=[
            NormalizedIngredient(raw_text="Water", normalized_name="water", matched=True)
        ],
        created_at="2026-01-01T00:00:00Z",
    )
    assert len(product.normalized_ingredients) == 1
