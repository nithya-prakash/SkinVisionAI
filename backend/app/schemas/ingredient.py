"""Ingredient schemas: parsed/normalized ingredients, compatibility rules,
and the structured compatibility-check result.

Phase 4 implements the deterministic parser/normalizer/compatibility
engine that produces these shapes (``app/ingredients/``). The LLM never
computes any of this -- see docs/agent.md and docs/ingredients.md.
"""
from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER


class IngredientCategory(StrEnum):
    """Broad functional category for a known ingredient.

    Deliberately small and coarse for a portfolio-scope engine; not an
    exhaustive cosmetic-chemistry taxonomy. An ingredient may belong to
    more than one category (e.g. niacinamide is both barrier_support and
    brightening) -- see ``NormalizedIngredient.categories``.
    """

    RETINOID = "retinoid"
    AHA = "aha"
    BHA = "bha"
    EXFOLIANT = "exfoliant"
    VITAMIN_C = "vitamin_c"
    ANTIOXIDANT = "antioxidant"
    HUMECTANT = "humectant"
    OCCLUSIVE = "occlusive"
    BARRIER_SUPPORT = "barrier_support"
    BRIGHTENING = "brightening"
    SOOTHING_AGENT = "soothing_agent"
    SUNSCREEN_FILTER = "sunscreen_filter"
    ACNE_TREATMENT = "acne_treatment"
    PRESERVATIVE = "preservative"
    FRAGRANCE = "fragrance"
    OTHER = "other"


class Ingredient(BaseModel):
    """A single canonical ingredient entry, as loaded from
    ``rules/ingredients/aliases.json`` + ``categories.json``.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(min_length=1, max_length=128)
    aliases: list[str] = Field(default_factory=list)
    categories: list[IngredientCategory] = Field(default_factory=list)


class NormalizedIngredient(BaseModel):
    """One token from a parsed ingredient list, resolved (or not) to a
    known ingredient.

    ``matched=False`` means the parser did not recognize the token -- it
    is surfaced as-is rather than guessed at. ``ambiguous=True`` means the
    token is a *known* alias that maps to more than one canonical
    ingredient (e.g. "Vitamin A" could mean retinol, retinaldehyde, retinyl
    palmitate, or tretinoin) -- the engine deliberately does not guess
    which one; ``candidates`` lists the possibilities.
    """

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(min_length=1)
    normalized_name: str | None = None
    matched: bool = False
    ambiguous: bool = False
    candidates: list[str] = Field(default_factory=list)
    categories: list[IngredientCategory] = Field(default_factory=list)


class RuleSeverity(StrEnum):
    """How significant a documented ingredient interaction is.

    Not every interaction is a warning -- most real-world combinations are
    informational, or simply unrepresented in this small, curated rule
    set (``no_known_conflict``, which is never proof of safety).
    """

    INCOMPATIBILITY = "incompatibility"
    CAUTION = "caution"
    INFORMATIONAL = "informational"
    NO_KNOWN_CONFLICT = "no_known_conflict"


class IngredientInteraction(BaseModel):
    """One documented (or explicitly absent) interaction between two ingredients.

    Every field here is sourced from the versioned rule file
    (``backend/rules/ingredients/compatibility.json``) -- the LLM never
    generates any of this. ``source``/``source_url``/``reason`` are
    required in the rule file for real findings (validated at load time by
    ``app.ingredients.rules``); a ``no_known_conflict`` result (only ever
    produced dynamically, never stored in the rule file) has no rule_id or
    source because it asserts nothing.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None
    ingredient_a: str
    ingredient_b: str
    severity: RuleSeverity
    message: str = Field(min_length=1)
    reason: str | None = None
    source: str | None = None
    source_url: str | None = None
    last_verified: date | None = None


class CompatibilityResult(BaseModel):
    """Structured output of the deterministic compatibility engine.

    This is the only shape ingredient-compatibility findings are returned
    in anywhere in this system. See docs/ingredients.md for the full
    severity model, source policy, and how to add a new rule.
    """

    model_config = ConfigDict(extra="forbid")

    ingredients: list[NormalizedIngredient]
    interactions: list[IngredientInteraction] = Field(default_factory=list)
    unknown_ingredients: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
