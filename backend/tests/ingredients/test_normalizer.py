"""Table-driven tests for app.ingredients.normalizer, exercised against the
real, default versioned rule set (offline, no network/LLM involved).
"""
from __future__ import annotations

import pytest

from app.ingredients.normalizer import normalize_ingredient, normalize_ingredient_list
from app.ingredients.rules import get_rule_set

RULE_SET = get_rule_set()


@pytest.mark.parametrize(
    "raw_text,expected_canonical",
    [
        ("water", "water"),
        ("Water", "water"),
        ("WATER", "water"),
        ("  water  ", "water"),
        ("Aqua", "water"),
        ("aqua", "water"),
        ("Eau", "water"),
        ("Niacinamide", "niacinamide"),
        ("niacinamide", "niacinamide"),
        ("Nicotinamide", "niacinamide"),
        ("Vitamin B3", "niacinamide"),
        ("vitamin   b3", "niacinamide"),  # extra internal whitespace
        ("Retinol", "retinol"),
        ("Glycolic Acid", "glycolic_acid"),
        ("Salicylic Acid", "salicylic_acid"),
        ("BHA", "salicylic_acid"),
        ("Ascorbic Acid", "ascorbic_acid"),
        ("L-Ascorbic Acid", "ascorbic_acid"),
        ("Panthenol", "panthenol"),
        ("Pro-Vitamin B5", "panthenol"),
    ],
)
def test_normalize_known_aliases_and_canonical_names(raw_text: str, expected_canonical: str) -> None:
    result = normalize_ingredient(raw_text, RULE_SET)
    assert result.matched is True
    assert result.normalized_name == expected_canonical
    assert result.raw_text == raw_text  # original text preserved verbatim


def test_normalize_unknown_ingredient_is_not_invented() -> None:
    result = normalize_ingredient("NovelComplexXYZ", RULE_SET)
    assert result.matched is False
    assert result.normalized_name is None
    assert result.ambiguous is False
    assert result.categories == []


@pytest.mark.parametrize("raw_text", ["Vitamin A", "vitamin a", "  Vitamin A  "])
def test_normalize_ambiguous_alias_does_not_guess(raw_text: str) -> None:
    result = normalize_ingredient(raw_text, RULE_SET)
    assert result.matched is False
    assert result.ambiguous is True
    assert result.normalized_name is None
    assert "retinol" in result.candidates
    assert "tretinoin" in result.candidates


def test_normalize_vitamin_c_is_ambiguous() -> None:
    result = normalize_ingredient("Vitamin C", RULE_SET)
    assert result.ambiguous is True
    assert result.matched is False
    assert set(result.candidates) == {
        "ascorbic_acid",
        "sodium_ascorbyl_phosphate",
        "magnesium_ascorbyl_phosphate",
    }


def test_normalize_reports_ingredient_categories() -> None:
    result = normalize_ingredient("Retinol", RULE_SET)
    assert "retinoid" in result.categories


def test_normalize_ingredient_with_multiple_categories() -> None:
    result = normalize_ingredient("Niacinamide", RULE_SET)
    assert "barrier_support" in result.categories
    assert "brightening" in result.categories


def test_normalize_ingredient_list_preserves_order_and_count() -> None:
    tokens = ["Water", "Niacinamide", "NovelComplexXYZ", "Glycerin"]
    results = normalize_ingredient_list(tokens, RULE_SET)
    assert len(results) == 4
    assert [r.raw_text for r in results] == tokens
    assert [r.matched for r in results] == [True, True, False, True]


def test_normalize_is_deterministic() -> None:
    first = normalize_ingredient("Retinol", RULE_SET)
    second = normalize_ingredient("Retinol", RULE_SET)
    assert first == second
