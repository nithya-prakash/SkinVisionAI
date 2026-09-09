"""Tests for app.routine.overlap -- duplicate/overlapping active detection.

Uses the real, shipped default rule sets (offline, no network/LLM).
"""
from __future__ import annotations

from app.ingredients.normalizer import normalize_ingredient_list
from app.ingredients.parser import parse_ingredient_list
from app.ingredients.rules import get_rule_set
from app.routine.overlap import find_overlapping_actives
from app.routine.rules import get_routine_rule_set

INGREDIENT_RULES = get_rule_set()
ROUTINE_RULES = get_routine_rule_set()


def _product(name: str, raw_text: str):
    tokens = parse_ingredient_list(raw_text)
    normalized = normalize_ingredient_list(tokens, INGREDIENT_RULES)
    return (name, normalized)


def test_no_overlap_between_unrelated_products() -> None:
    products = [
        _product("Product A", "Water, Glycerin"),
        _product("Product B", "Water, Panthenol"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert overlaps == []


def test_one_duplicated_active_across_two_products() -> None:
    products = [
        _product("Product A", "Retinol, Niacinamide"),
        _product("Product B", "Retinol, Hyaluronic Acid"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert len(overlaps) == 1
    overlap = overlaps[0]
    assert overlap.ingredient == "retinol"
    assert overlap.count == 2
    assert set(overlap.products) == {"Product A", "Product B"}
    assert "retinoid" in overlap.categories


def test_multiple_duplicated_actives() -> None:
    products = [
        _product("Product A", "Retinol, Salicylic Acid"),
        _product("Product B", "Retinol, Salicylic Acid"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    ingredients = {o.ingredient for o in overlaps}
    assert ingredients == {"retinol", "salicylic_acid"}


def test_same_ingredient_appearing_in_three_products() -> None:
    products = [
        _product("A", "Niacinamide"),
        _product("B", "Niacinamide"),
        _product("C", "Niacinamide"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    # Niacinamide is barrier_support/brightening, not in the active_categories
    # list (retinoid/aha/bha/vitamin_c/acne_treatment) -- so no overlap finding.
    assert overlaps == []


def test_same_active_appearing_in_three_products() -> None:
    products = [
        _product("A", "Retinol"),
        _product("B", "Retinol"),
        _product("C", "Retinol"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert len(overlaps) == 1
    assert overlaps[0].count == 3
    assert set(overlaps[0].products) == {"A", "B", "C"}


def test_case_differences_still_detected_as_the_same_ingredient() -> None:
    products = [
        _product("A", "RETINOL"),
        _product("B", "retinol"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert len(overlaps) == 1
    assert overlaps[0].count == 2


def test_aliases_resolve_to_the_same_canonical_ingredient() -> None:
    products = [
        _product("A", "Nicotinamide"),  # alias of niacinamide -- not an "active" category though
        _product("B", "Vitamin B3"),
    ]
    # niacinamide isn't in active_categories, so no overlap finding is
    # expected here -- but both should resolve to the SAME canonical name.
    tokens_a = normalize_ingredient_list(parse_ingredient_list("Nicotinamide"), INGREDIENT_RULES)
    tokens_b = normalize_ingredient_list(parse_ingredient_list("Vitamin B3"), INGREDIENT_RULES)
    assert tokens_a[0].normalized_name == tokens_b[0].normalized_name == "niacinamide"


def test_alias_overlap_for_an_active_category_is_detected() -> None:
    products = [
        _product("A", "Ascorbic Acid"),
        _product("B", "L-Ascorbic Acid"),  # alias of ascorbic_acid, vitamin_c category
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert len(overlaps) == 1
    assert overlaps[0].ingredient == "ascorbic_acid"


def test_unknown_ingredients_never_produce_an_overlap_finding() -> None:
    products = [
        _product("A", "NovelComplexXYZ"),
        _product("B", "NovelComplexXYZ"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert overlaps == []


def test_duplicate_ingredient_within_one_product_does_not_inflate_count() -> None:
    products = [
        _product("A", "Retinol, Retinol"),  # duplicate token within the same product
        _product("B", "Retinol"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert len(overlaps) == 1
    assert overlaps[0].count == 2  # 2 distinct products, not 3 occurrences


def test_overlap_message_is_sourced_and_deterministic_message() -> None:
    products = [_product("A", "Retinol"), _product("B", "Retinol")]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    assert overlaps[0].source is not None
    assert overlaps[0].source_url.startswith("https://")
    assert "irritation" in overlaps[0].message.lower()


def test_overlap_results_are_sorted_by_ingredient_name() -> None:
    products = [
        _product("A", "Salicylic Acid, Retinol"),
        _product("B", "Salicylic Acid, Retinol"),
    ]
    overlaps = find_overlapping_actives(products, ROUTINE_RULES, INGREDIENT_RULES)
    names = [o.ingredient for o in overlaps]
    assert names == sorted(names)
