"""Tests for app.products.comparator -- deterministic product comparison.

Uses the real, shipped default ingredient rule set (offline, no
network/LLM).
"""
from __future__ import annotations

from app.products.comparator import compare_products
from app.schemas.ingredient import RuleSeverity
from app.schemas.product import ProductCompareItem, ProductCompareRequest


def _request(name_a, ingredients_a, name_b, ingredients_b) -> ProductCompareRequest:
    return ProductCompareRequest(
        product_a=ProductCompareItem(name=name_a, raw_ingredient_text=ingredients_a),
        product_b=ProductCompareItem(name=name_b, raw_ingredient_text=ingredients_b),
    )


def test_identical_products() -> None:
    result = compare_products(_request("A", "Water, Niacinamide", "B", "Water, Niacinamide"))
    assert set(result.shared_ingredients) == {"water", "niacinamide"}
    assert result.only_in_a == []
    assert result.only_in_b == []


def test_completely_different_products() -> None:
    result = compare_products(_request("A", "Water", "B", "Glycerin"))
    assert result.shared_ingredients == []
    assert result.only_in_a == ["water"]
    assert result.only_in_b == ["glycerin"]


def test_partially_overlapping_products_from_master_spec_example() -> None:
    """Product A: Retinol, Niacinamide, Glycerin
    Product B: Retinol, Salicylic Acid, Glycerin
    -> shared: retinol, glycerin; only A: niacinamide; only B: salicylic acid
    -> interactions: retinol + salicylic acid (caution, cross-product) AND
       retinol + niacinamide (informational, within product A) -- the real
       shipped rule set has both, so both are correctly expected here.
    """
    result = compare_products(
        _request(
            "Product A", "Retinol, Niacinamide, Glycerin",
            "Product B", "Retinol, Salicylic Acid, Glycerin",
        )
    )
    assert set(result.shared_ingredients) == {"retinol", "glycerin"}
    assert result.only_in_a == ["niacinamide"]
    assert result.only_in_b == ["salicylic_acid"]

    by_rule_id = {i.rule_id: i for i in result.interactions}
    assert set(by_rule_id) == {"retinol_salicylic_acid_caution", "retinol_niacinamide_informational"}
    assert by_rule_id["retinol_salicylic_acid_caution"].severity == RuleSeverity.CAUTION
    assert by_rule_id["retinol_niacinamide_informational"].severity == RuleSeverity.INFORMATIONAL


def test_shared_active_categories() -> None:
    result = compare_products(_request("A", "Retinol", "B", "Retinaldehyde"))
    assert "retinoid" in result.shared_categories


def test_no_shared_categories_when_none_overlap() -> None:
    result = compare_products(_request("A", "Water", "B", "Glycerin"))
    # water has no categories; glycerin is humectant -- no overlap
    assert result.shared_categories == []


def test_unknown_ingredients_reported_per_product() -> None:
    result = compare_products(_request("A", "NovelComplexXYZ", "B", "Water"))
    assert result.unknown_ingredients_a == ["NovelComplexXYZ"]
    assert result.unknown_ingredients_b == []


def test_no_overall_score_field_exists() -> None:
    result = compare_products(_request("A", "Retinol", "B", "Water"))
    dumped = result.model_dump()
    for banned_key in ("score", "better_product", "winner", "rating"):
        assert banned_key not in dumped


def test_comparison_is_deterministic() -> None:
    request = _request("A", "Retinol, Glycolic Acid", "B", "Salicylic Acid, Niacinamide")
    first = compare_products(request)
    second = compare_products(request)
    assert first.model_dump() == second.model_dump()


def test_comparison_never_says_safe() -> None:
    result = compare_products(_request("A", "Water", "B", "Glycerin"))
    full_text = " ".join(result.limitations).lower()
    assert "safe" not in full_text
