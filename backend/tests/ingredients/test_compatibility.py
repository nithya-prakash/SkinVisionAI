"""Tests for app.ingredients.compatibility -- the deterministic engine.

Uses the real, shipped default rule set (offline, no network/LLM) for
known-case tests, so these tests double as documentation of the actual
current rule set's behavior.
"""
from __future__ import annotations

from app.ingredients.compatibility import check_ingredient_compatibility, check_pair
from app.ingredients.rules import get_rule_set
from app.schemas.ingredient import RuleSeverity

RULE_SET = get_rule_set()


# --- check_ingredient_compatibility: known cases from the real rule set ---


def test_caution_case_retinol_and_glycolic_acid() -> None:
    result = check_ingredient_compatibility(["Retinol", "Glycolic Acid"])
    assert len(result.interactions) == 1
    interaction = result.interactions[0]
    assert interaction.severity == RuleSeverity.CAUTION
    assert interaction.source == "Cleveland Clinic"
    assert interaction.source_url.startswith("https://")


def test_informational_case_retinol_and_niacinamide() -> None:
    result = check_ingredient_compatibility(["Retinol", "Niacinamide"])
    assert len(result.interactions) == 1
    assert result.interactions[0].severity == RuleSeverity.INFORMATIONAL


def test_no_known_conflict_case_water_and_glycerin() -> None:
    """Two ordinary, unrelated ingredients with no authored rule between
    them: no interaction is fabricated for the bulk-list check.
    """
    result = check_ingredient_compatibility(["Water", "Glycerin"])
    assert result.interactions == []
    assert any("no rule exists" in note for note in result.limitations)


def test_reverse_order_produces_the_same_interaction() -> None:
    forward = check_ingredient_compatibility(["Retinol", "Glycolic Acid"])
    reverse = check_ingredient_compatibility(["Glycolic Acid", "Retinol"])
    assert forward.interactions[0].rule_id == reverse.interactions[0].rule_id
    assert forward.interactions[0].severity == reverse.interactions[0].severity


def test_duplicate_ingredients_do_not_duplicate_findings() -> None:
    result = check_ingredient_compatibility(["Niacinamide", "Niacinamide", "Retinol"])
    assert len(result.interactions) == 1  # not 2, despite niacinamide appearing twice
    assert len(result.ingredients) == 3  # every original token still present


def test_unknown_ingredients_reported_separately_not_as_errors() -> None:
    result = check_ingredient_compatibility(["Water", "NovelComplexXYZ"])
    assert "NovelComplexXYZ" in result.unknown_ingredients
    assert result.interactions == []


def test_empty_ingredient_list() -> None:
    result = check_ingredient_compatibility([])
    assert result.ingredients == []
    assert result.interactions == []
    assert result.unknown_ingredients == []
    assert result.limitations != []  # general limitation always present


def test_malformed_tokens_do_not_crash_the_engine() -> None:
    result = check_ingredient_compatibility(["", "   ", "Water"])
    # empty/whitespace tokens fail min_length at the schema boundary and
    # are simply not meaningful ingredients -- the engine should not crash
    matched = [ing for ing in result.ingredients if ing.matched]
    assert any(ing.normalized_name == "water" for ing in matched)


def test_result_always_carries_the_general_limitation() -> None:
    result = check_ingredient_compatibility(["Water"])
    assert any("concentration" in note for note in result.limitations)


def test_compatibility_result_is_deterministic() -> None:
    tokens = ["Retinol", "Glycolic Acid", "Niacinamide", "Water"]
    first = check_ingredient_compatibility(tokens)
    second = check_ingredient_compatibility(tokens)
    assert first.model_dump() == second.model_dump()


def test_multiple_interactions_when_multiple_rules_apply() -> None:
    result = check_ingredient_compatibility(
        ["Retinol", "Glycolic Acid", "Salicylic Acid", "Niacinamide"]
    )
    rule_ids = {i.rule_id for i in result.interactions}
    assert "retinol_glycolic_acid_caution" in rule_ids
    assert "retinol_salicylic_acid_caution" in rule_ids
    assert "retinol_niacinamide_informational" in rule_ids


# --- Safety wording: the engine must never overclaim ---


def test_unknown_ingredient_result_never_says_safe() -> None:
    result = check_ingredient_compatibility(["NovelComplexXYZ"])
    ingredient = result.ingredients[0]
    assert ingredient.matched is False
    # nothing in the result should claim this unknown ingredient is safe
    full_text = " ".join(result.limitations)
    assert "safe" not in full_text.lower()


def test_no_known_conflict_never_claims_definite_safety() -> None:
    interaction = check_pair("water", "glycerin")
    assert interaction.severity == RuleSeverity.NO_KNOWN_CONFLICT
    assert "safe" not in interaction.message.lower()
    assert "no known conflict" in interaction.message.lower()


def test_caution_rule_does_not_use_dangerous_language_unless_sourced() -> None:
    result = check_ingredient_compatibility(["Retinol", "Glycolic Acid"])
    message = result.interactions[0].message.lower()
    assert "dangerous" not in message
    assert "unsafe" not in message


# --- check_pair: single-pair mode, always returns a result ---


def test_check_pair_known_caution() -> None:
    interaction = check_pair("Retinol", "Salicylic Acid")
    assert interaction.severity == RuleSeverity.CAUTION
    assert interaction.rule_id == "retinol_salicylic_acid_caution"


def test_check_pair_reverse_order_matches_same_rule() -> None:
    a = check_pair("Retinol", "Benzoyl Peroxide")
    b = check_pair("Benzoyl Peroxide", "Retinol")
    assert a.rule_id == b.rule_id


def test_check_pair_no_known_conflict_for_unrelated_known_ingredients() -> None:
    interaction = check_pair("Water", "Glycerin")
    assert interaction.severity == RuleSeverity.NO_KNOWN_CONFLICT
    assert interaction.rule_id is None
    assert interaction.source is None


def test_check_pair_unknown_ingredient_reports_unsupported_not_unsafe() -> None:
    interaction = check_pair("Water", "NovelComplexXYZ")
    assert interaction.severity == RuleSeverity.NO_KNOWN_CONFLICT
    assert "No supported rule" in interaction.message
    assert "NovelComplexXYZ" in interaction.message


def test_check_pair_ambiguous_alias_is_treated_as_unresolved() -> None:
    interaction = check_pair("Vitamin A", "Water")
    assert interaction.severity == RuleSeverity.NO_KNOWN_CONFLICT
    assert "No supported rule" in interaction.message


def test_check_pair_is_deterministic() -> None:
    first = check_pair("Retinol", "Glycolic Acid")
    second = check_pair("Retinol", "Glycolic Acid")
    assert first.model_dump() == second.model_dump()
