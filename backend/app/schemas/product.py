"""Product schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER, ProductCategory
from app.schemas.ingredient import CompatibilityResult, IngredientCategory, IngredientInteraction, NormalizedIngredient


class ProductBase(BaseModel):
    """Fields common to product creation and reads."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    category: ProductCategory | None = None
    raw_ingredient_text: str | None = Field(
        default=None,
        description='Free-text ingredient list, e.g. "Water, Niacinamide, Glycerin".',
    )


class ProductCreate(ProductBase):
    """Payload accepted when a user enters a product."""

    session_id: UUID


class ProductRead(ProductBase):
    """Product as returned by the API, including its parsed ingredient list."""

    id: UUID
    session_id: UUID
    normalized_ingredients: list[NormalizedIngredient] = Field(default_factory=list)
    created_at: datetime


class ProductAnalyzeRequest(BaseModel):
    """Payload for ``POST /api/products/analyze`` (Phase 4)."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    category: ProductCategory | None = None
    raw_ingredient_text: str = Field(min_length=1)


class ProductAnalyzeResponse(BaseModel):
    """Response for ``POST /api/products/analyze`` (Phase 4): the product's
    identity plus its full deterministic compatibility-engine result.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    session_id: UUID
    name: str
    category: ProductCategory | None
    compatibility: CompatibilityResult


# --- Phase 5: stateless product-vs-product comparison ---
# Stateless by default -- see docs/routine.md for why. Phase 8 adds an
# opt-in ``persist`` flag (default False, byte-identical behavior for
# every existing caller) -- see docs/persistence.md.


class ProductCompareItem(BaseModel):
    """One of the two products submitted to ``POST /api/products/compare``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    category: ProductCategory | None = None
    raw_ingredient_text: str = Field(min_length=1)


class ProductCompareRequest(BaseModel):
    """Payload for ``POST /api/products/compare`` (Phase 5)."""

    model_config = ConfigDict(extra="forbid")

    product_a: ProductCompareItem
    product_b: ProductCompareItem
    session_id: UUID | None = Field(
        default=None,
        description="Only used when persist=True; attaches the persisted record to an existing session.",
    )
    persist: bool = Field(
        default=False,
        description="Phase 8 opt-in: when True, persists this request+result as a ComparisonRecord and returns its id.",
    )


class ProductComparisonResult(BaseModel):
    """Deterministic comparison of two products' ingredients.

    Deliberately has no overall "better product" score or verdict field --
    see docs/ingredients.md's wording policy, which applies here too.
    """

    model_config = ConfigDict(extra="forbid")

    product_a_name: str
    product_b_name: str
    shared_ingredients: list[str] = Field(default_factory=list)
    only_in_a: list[str] = Field(default_factory=list)
    only_in_b: list[str] = Field(default_factory=list)
    shared_categories: list[IngredientCategory] = Field(default_factory=list)
    interactions: list[IngredientInteraction] = Field(default_factory=list)
    unknown_ingredients_a: list[str] = Field(default_factory=list)
    unknown_ingredients_b: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    id: UUID | None = Field(
        default=None,
        description="Set only when the request had persist=True (Phase 8) -- the ComparisonRecord id.",
    )
