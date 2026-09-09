"""Routine schemas: persisted AM/PM sequences of products (Phase 1), and
the Phase 5 stateless routine-analysis request/result.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER, ProductCategory, TimeOfDay, TimeOfDayPreference
from app.schemas.ingredient import IngredientCategory, NormalizedIngredient, RuleSeverity


class RoutineItemBase(BaseModel):
    """Fields common to routine item creation and reads."""

    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    time_of_day: TimeOfDay
    step_order: int = Field(ge=0, default=0)


class RoutineItemCreate(RoutineItemBase):
    """Payload accepted when adding a product to a routine."""


class RoutineItemRead(RoutineItemBase):
    """Routine item as returned by the API."""

    id: UUID
    routine_id: UUID


class RoutineBase(BaseModel):
    """Fields common to routine creation and reads."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128, default="My Routine")


class RoutineCreate(RoutineBase):
    """Payload accepted when creating a routine, optionally pre-populated with items."""

    session_id: UUID
    items: list[RoutineItemCreate] = Field(default_factory=list)


class RoutineRead(RoutineBase):
    """Routine as returned by the API."""

    id: UUID
    session_id: UUID
    items: list[RoutineItemRead] = Field(default_factory=list)
    created_at: datetime


# --- Phase 5: stateless routine analysis ---
#
# Distinct from RoutineCreate/Read above: this is an ad-hoc, ephemeral
# analysis over a user-supplied list of products (which need not already
# exist as persisted Product rows) -- nothing here is written to the
# database by default. See docs/routine.md for why this is stateless by
# design. Phase 8 adds an opt-in ``persist`` flag (default False, so
# every existing caller sees byte-identical behavior) -- see
# docs/persistence.md.


class RoutineProductInput(BaseModel):
    """One product entered for routine analysis.

    ``category`` and ``time_of_day`` are self-reported/optional; the
    engine never fabricates either when omitted -- see
    ``app.routine.ordering``.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(min_length=1, max_length=255)
    raw_ingredients: str = Field(min_length=1)
    category: ProductCategory | None = None
    intended_use: str | None = Field(default=None, max_length=255)
    time_of_day: TimeOfDayPreference = TimeOfDayPreference.UNSPECIFIED


class RoutineAnalysisRequest(BaseModel):
    """Payload for ``POST /api/routine/analyze``."""

    model_config = ConfigDict(extra="forbid")

    products: list[RoutineProductInput] = Field(min_length=1)
    session_id: UUID | None = Field(
        default=None,
        description="Only used when persist=True; attaches the persisted record to an existing session.",
    )
    persist: bool = Field(
        default=False,
        description="Phase 8 opt-in: when True, persists this request+result as a RoutineAnalysisRecord and returns its id.",
    )


class RoutineProductAnalysis(BaseModel):
    """One input product's parsed/normalized ingredients, echoed back
    alongside the rest of the analysis for traceability.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str
    category: ProductCategory | None
    time_of_day: TimeOfDayPreference
    normalized_ingredients: list[NormalizedIngredient]


class OverlappingActive(BaseModel):
    """One active ingredient found in two or more of the input products."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str
    categories: list[IngredientCategory]
    products: list[str] = Field(min_length=2)
    count: int = Field(ge=2)
    message: str
    reason: str | None = None
    source: str | None = None
    source_url: str | None = None
    last_verified: date | None = None


class RoutineInteraction(BaseModel):
    """One compatibility-engine finding (Phase 4, reused verbatim) plus
    which input product(s) contributed the two ingredients involved.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    ingredient_a: str
    ingredient_b: str
    severity: RuleSeverity
    message: str
    reason: str | None = None
    source: str | None = None
    source_url: str | None = None
    last_verified: date | None = None
    products: list[str]


class ScheduledStep(BaseModel):
    """One product placed at a deterministic position in a suggested
    AM or PM sequence.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str
    category: ProductCategory
    step_order: int = Field(ge=0)


class UnscheduledProduct(BaseModel):
    """A product the engine could not place in a suggested sequence, and
    exactly why -- never a fabricated position.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str
    reason: str


class RoutineAnalysisResult(BaseModel):
    """Structured output of the deterministic routine engine (Phase 5)."""

    model_config = ConfigDict(extra="forbid")

    products: list[RoutineProductAnalysis]
    overlapping_actives: list[OverlappingActive] = Field(default_factory=list)
    interactions: list[RoutineInteraction] = Field(default_factory=list)
    suggested_am: list[ScheduledStep] = Field(default_factory=list)
    suggested_pm: list[ScheduledStep] = Field(default_factory=list)
    unscheduled_products: list[UnscheduledProduct] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    id: UUID | None = Field(
        default=None,
        description="Set only when the request had persist=True (Phase 8) -- the RoutineAnalysisRecord id.",
    )
