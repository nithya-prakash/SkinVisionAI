"""Tests for app.schemas.ingredient."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ingredient import (
    CompatibilityResult,
    Ingredient,
    IngredientCategory,
    IngredientInteraction,
    NormalizedIngredient,
    RuleSeverity,
)


def test_ingredient_valid_with_defaults() -> None:
    ing = Ingredient(canonical_name="niacinamide")
    assert ing.aliases == []
    assert ing.categories == []


def test_ingredient_with_aliases_and_categories() -> None:
    ing = Ingredient(
        canonical_name="retinol",
        aliases=["retinyl palmitate", "vitamin a"],
        categories=[IngredientCategory.RETINOID],
    )
    assert "retinyl palmitate" in ing.aliases
    assert IngredientCategory.RETINOID in ing.categories


def test_ingredient_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Ingredient(canonical_name="")


def test_ingredient_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        Ingredient(canonical_name="water", categories=["miracle_cure"])


def test_ingredient_can_have_multiple_categories() -> None:
    ing = Ingredient(
        canonical_name="niacinamide",
        categories=[IngredientCategory.BARRIER_SUPPORT, IngredientCategory.BRIGHTENING],
    )
    assert len(ing.categories) == 2


def test_normalized_ingredient_matched() -> None:
    result = NormalizedIngredient(
        raw_text="Niacinamide",
        normalized_name="niacinamide",
        matched=True,
        categories=[IngredientCategory.SOOTHING_AGENT],
    )
    assert result.matched is True


def test_normalized_ingredient_unmatched_token_is_not_invented() -> None:
    result = NormalizedIngredient(raw_text="SomeMadeUpCompoundXYZ")
    assert result.matched is False
    assert result.normalized_name is None
    assert result.categories == []
    assert result.ambiguous is False
    assert result.candidates == []


def test_normalized_ingredient_ambiguous_alias_lists_candidates() -> None:
    result = NormalizedIngredient(
        raw_text="Vitamin A",
        matched=False,
        ambiguous=True,
        candidates=["retinol", "tretinoin"],
    )
    assert result.ambiguous is True
    assert result.normalized_name is None
    assert set(result.candidates) == {"retinol", "tretinoin"}


def test_normalized_ingredient_rejects_empty_raw_text() -> None:
    with pytest.raises(ValidationError):
        NormalizedIngredient(raw_text="")


# --- IngredientInteraction / RuleSeverity ---


def test_ingredient_interaction_valid_caution() -> None:
    interaction = IngredientInteraction(
        rule_id="retinol_glycolic_acid_caution",
        ingredient_a="retinol",
        ingredient_b="glycolic_acid",
        severity=RuleSeverity.CAUTION,
        message="May increase irritation.",
        reason="Both can irritate skin on their own.",
        source="Cleveland Clinic",
        source_url="https://my.clevelandclinic.org/health/treatments/23293-retinol",
        last_verified="2026-09-08",
    )
    assert interaction.severity == RuleSeverity.CAUTION


def test_ingredient_interaction_no_known_conflict_has_no_source() -> None:
    interaction = IngredientInteraction(
        ingredient_a="water",
        ingredient_b="glycerin",
        severity=RuleSeverity.NO_KNOWN_CONFLICT,
        message="No known conflict is represented in the current rule set for this pair.",
    )
    assert interaction.rule_id is None
    assert interaction.source is None


def test_ingredient_interaction_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        IngredientInteraction(
            ingredient_a="a", ingredient_b="b", severity="extremely_dangerous", message="x"
        )


def test_ingredient_interaction_requires_message() -> None:
    with pytest.raises(ValidationError):
        IngredientInteraction(
            ingredient_a="a", ingredient_b="b", severity=RuleSeverity.INFORMATIONAL, message=""
        )


def test_ingredient_interaction_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IngredientInteraction(
            ingredient_a="a",
            ingredient_b="b",
            severity=RuleSeverity.CAUTION,
            message="x",
            confidence_percent=90,
        )


# --- CompatibilityResult ---


def test_compatibility_result_valid() -> None:
    result = CompatibilityResult(
        ingredients=[NormalizedIngredient(raw_text="Water", normalized_name="water", matched=True)],
        interactions=[],
        unknown_ingredients=[],
        limitations=["Depends on concentration and formulation."],
    )
    assert result.disclaimer.startswith("SkinVision AI provides educational")


def test_compatibility_result_defaults() -> None:
    result = CompatibilityResult(ingredients=[])
    assert result.interactions == []
    assert result.unknown_ingredients == []
    assert result.limitations == []


def test_compatibility_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CompatibilityResult(ingredients=[], overall_safety_score=95)
