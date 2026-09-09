"""Tests for app.routine.analyzer -- the full Phase 5 orchestration.

Uses the real, shipped default rule sets (offline, no network/LLM).
"""
from __future__ import annotations

from app.routine.analyzer import analyze_routine
from app.schemas.common import ProductCategory, TimeOfDayPreference
from app.schemas.ingredient import RuleSeverity
from app.schemas.routine import RoutineAnalysisRequest, RoutineProductInput


def _request(*products: RoutineProductInput) -> RoutineAnalysisRequest:
    return RoutineAnalysisRequest(products=list(products))


def _p(name, ingredients, category=None, time_of_day=TimeOfDayPreference.UNSPECIFIED):
    return RoutineProductInput(
        product_name=name,
        raw_ingredients=ingredients,
        category=category,
        time_of_day=time_of_day,
    )


# --- Compatibility: no interaction / caution / informational / multiple ---


def test_no_interaction_between_unrelated_products() -> None:
    result = analyze_routine(_request(_p("A", "Water, Glycerin"), _p("B", "Water, Panthenol")))
    assert result.interactions == []


def test_caution_interaction_across_two_products() -> None:
    result = analyze_routine(
        _request(_p("Retinol Serum", "Retinol"), _p("Acid Toner", "Glycolic Acid"))
    )
    assert len(result.interactions) == 1
    interaction = result.interactions[0]
    assert interaction.severity == RuleSeverity.CAUTION
    assert set(interaction.products) == {"Retinol Serum", "Acid Toner"}


def test_informational_interaction_across_two_products() -> None:
    result = analyze_routine(
        _request(_p("Retinol Serum", "Retinol"), _p("Niacinamide Serum", "Niacinamide"))
    )
    assert len(result.interactions) == 1
    assert result.interactions[0].severity == RuleSeverity.INFORMATIONAL


def test_multiple_interactions_across_products() -> None:
    result = analyze_routine(
        _request(
            _p("Retinol Serum", "Retinol"),
            _p("Acid Toner", "Glycolic Acid, Salicylic Acid"),
        )
    )
    rule_ids = {i.rule_id for i in result.interactions}
    assert "retinol_glycolic_acid_caution" in rule_ids
    assert "retinol_salicylic_acid_caution" in rule_ids


def test_interaction_within_a_single_product_is_also_found() -> None:
    result = analyze_routine(_request(_p("Combo Serum", "Retinol, Glycolic Acid")))
    assert len(result.interactions) == 1
    assert result.interactions[0].products == ["Combo Serum"]


def test_same_interaction_via_multiple_products_is_deduplicated() -> None:
    """Retinol in product A interacts with glycolic acid in BOTH B and C --
    the underlying rule should be reported once, listing every involved
    product, not once per product pair.
    """
    result = analyze_routine(
        _request(
            _p("Retinol Serum", "Retinol"),
            _p("Morning Acid", "Glycolic Acid"),
            _p("Evening Acid", "Glycolic Acid"),
        )
    )
    assert len(result.interactions) == 1
    assert set(result.interactions[0].products) == {"Retinol Serum", "Morning Acid", "Evening Acid"}


def test_reverse_ingredient_order_across_products_same_interaction() -> None:
    forward = analyze_routine(_request(_p("A", "Retinol"), _p("B", "Salicylic Acid")))
    reverse = analyze_routine(_request(_p("A", "Salicylic Acid"), _p("B", "Retinol")))
    assert forward.interactions[0].rule_id == reverse.interactions[0].rule_id


# --- Overlap ---


def test_overlapping_actives_reported() -> None:
    result = analyze_routine(
        _request(_p("A", "Retinol, Niacinamide"), _p("B", "Retinol, Hyaluronic Acid"))
    )
    assert len(result.overlapping_actives) == 1
    assert result.overlapping_actives[0].ingredient == "retinol"


# --- Ordering ---


def test_suggested_am_and_pm_from_full_routine() -> None:
    result = analyze_routine(
        _request(
            _p("Cleanser", "Water", ProductCategory.CLEANSER, TimeOfDayPreference.AM_AND_PM),
            _p("Vitamin C Serum", "Ascorbic Acid", ProductCategory.SERUM, TimeOfDayPreference.AM),
            _p("Retinol", "Retinol", ProductCategory.TREATMENT, TimeOfDayPreference.PM),
            _p("Moisturizer", "Glycerin", ProductCategory.MOISTURIZER, TimeOfDayPreference.AM_AND_PM),
            _p("Sunscreen", "Zinc Oxide", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM),
        )
    )
    am_names = [s.product_name for s in result.suggested_am]
    pm_names = [s.product_name for s in result.suggested_pm]
    assert am_names == ["Cleanser", "Vitamin C Serum", "Moisturizer", "Sunscreen"]
    assert pm_names == ["Cleanser", "Retinol", "Moisturizer"]
    assert result.unscheduled_products == []


def test_unscheduled_products_reported_with_reasons() -> None:
    result = analyze_routine(_request(_p("Mystery Product", "Water", category=None)))
    assert len(result.unscheduled_products) == 1
    assert result.unscheduled_products[0].product_name == "Mystery Product"


# --- Unknown ingredients / safety wording ---


def test_unknown_ingredients_reported_per_product() -> None:
    result = analyze_routine(_request(_p("A", "NovelComplexXYZ")))
    assert result.products[0].normalized_ingredients[0].matched is False


def test_result_never_affirmatively_claims_safety() -> None:
    """The limitations text legitimately contains phrases like "not ...
    proven safe" (explicitly denying a safety claim) -- that's correct,
    honest wording, not an overclaim. This checks no *affirmative* safety
    claim appears (e.g. "is safe", "safe together").
    """
    result = analyze_routine(_request(_p("A", "Water, Glycerin"), _p("B", "Water, Panthenol")))
    full_text = " ".join(result.limitations).lower()
    assert "is safe" not in full_text
    assert "safe together" not in full_text
    assert "definitely safe" not in full_text


def test_result_always_carries_disclaimer() -> None:
    result = analyze_routine(_request(_p("A", "Water")))
    assert result.disclaimer.startswith("SkinVision AI provides educational")


# --- Determinism ---


def test_routine_analysis_is_deterministic() -> None:
    request = _request(
        _p("Retinol Serum", "Retinol", ProductCategory.TREATMENT, TimeOfDayPreference.PM),
        _p("Acid Toner", "Glycolic Acid", ProductCategory.TONER, TimeOfDayPreference.PM),
    )
    first = analyze_routine(request)
    second = analyze_routine(request)
    assert first.model_dump() == second.model_dump()
