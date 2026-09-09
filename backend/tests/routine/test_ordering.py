"""Tests for app.routine.ordering -- deterministic AM/PM suggestion.

Uses the real, shipped default ordering rules (offline, no network/LLM).
"""
from __future__ import annotations

from app.routine.ordering import suggest_ordering
from app.routine.rules import get_routine_rule_set
from app.schemas.common import ProductCategory, TimeOfDayPreference
from app.schemas.routine import RoutineProductInput

RULES = get_routine_rule_set()


def _p(name, category=None, time_of_day=TimeOfDayPreference.UNSPECIFIED) -> RoutineProductInput:
    return RoutineProductInput(
        product_name=name, raw_ingredients="Water", category=category, time_of_day=time_of_day
    )


def test_standard_am_routine_ordering() -> None:
    products = [
        _p("Cleanser", ProductCategory.CLEANSER, TimeOfDayPreference.AM),
        _p("Vitamin C Serum", ProductCategory.SERUM, TimeOfDayPreference.AM),
        _p("Moisturizer", ProductCategory.MOISTURIZER, TimeOfDayPreference.AM),
        _p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM),
    ]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert [step.product_name for step in am] == [
        "Cleanser",
        "Vitamin C Serum",
        "Moisturizer",
        "Sunscreen",
    ]
    assert pm == []
    assert unscheduled == []


def test_standard_pm_routine_ordering() -> None:
    products = [
        _p("Cleanser", ProductCategory.CLEANSER, TimeOfDayPreference.PM),
        _p("Retinol", ProductCategory.TREATMENT, TimeOfDayPreference.PM),
        _p("Moisturizer", ProductCategory.MOISTURIZER, TimeOfDayPreference.PM),
    ]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert [step.product_name for step in pm] == ["Cleanser", "Retinol", "Moisturizer"]
    assert am == []
    assert unscheduled == []


def test_sunscreen_gets_final_am_position() -> None:
    products = [
        _p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM),
        _p("Cleanser", ProductCategory.CLEANSER, TimeOfDayPreference.AM),
        _p("Moisturizer", ProductCategory.MOISTURIZER, TimeOfDayPreference.AM),
    ]
    am, _, _ = suggest_ordering(products, RULES)
    assert am[-1].product_name == "Sunscreen"


def test_sunscreen_auto_scheduled_am_even_with_unspecified_time() -> None:
    """The one documented exception: sunscreen is AM by definition."""
    products = [_p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.UNSPECIFIED)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert len(am) == 1
    assert am[0].product_name == "Sunscreen"
    assert unscheduled == []


def test_unknown_category_is_never_scheduled() -> None:
    products = [_p("Mystery Product", category=None, time_of_day=TimeOfDayPreference.AM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert am == []
    assert len(unscheduled) == 1
    assert "unknown" in unscheduled[0].reason.lower()


def test_unspecified_time_of_day_is_not_scheduled_for_non_sunscreen() -> None:
    products = [_p("Serum", ProductCategory.SERUM, TimeOfDayPreference.UNSPECIFIED)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert am == []
    assert pm == []
    assert len(unscheduled) == 1
    assert "not specified" in unscheduled[0].reason.lower()


def test_explicit_am_only_product_never_appears_in_pm() -> None:
    products = [_p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert len(am) == 1
    assert pm == []
    assert unscheduled == []


def test_explicit_pm_only_product_never_appears_in_am() -> None:
    products = [_p("Retinol", ProductCategory.TREATMENT, TimeOfDayPreference.PM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert am == []
    assert len(pm) == 1


def test_am_and_pm_product_appears_in_both() -> None:
    products = [_p("Moisturizer", ProductCategory.MOISTURIZER, TimeOfDayPreference.AM_AND_PM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert len(am) == 1
    assert len(pm) == 1
    assert unscheduled == []


def test_am_and_pm_sunscreen_only_appears_in_am_with_a_partial_note() -> None:
    """Sunscreen has no PM ordering rule -- AM_AND_PM sunscreen should
    still be placed in AM but not silently duplicated into PM.
    """
    products = [_p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM_AND_PM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert len(am) == 1
    assert pm == []
    assert unscheduled == []  # it WAS placed (in AM), just not in PM


def test_category_with_no_pm_rule_is_unscheduled_for_pm_only_request() -> None:
    products = [_p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.PM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert am == []
    assert pm == []
    assert len(unscheduled) == 1


def test_category_other_has_no_ordering_rule() -> None:
    products = [_p("Face Mist", ProductCategory.OTHER, TimeOfDayPreference.AM)]
    am, pm, unscheduled = suggest_ordering(products, RULES)
    assert am == []
    assert len(unscheduled) == 1


def test_ordering_is_deterministic() -> None:
    products = [
        _p("Cleanser", ProductCategory.CLEANSER, TimeOfDayPreference.AM),
        _p("Sunscreen", ProductCategory.SUNSCREEN, TimeOfDayPreference.AM),
    ]
    first = suggest_ordering(products, RULES)
    second = suggest_ordering(products, RULES)
    assert first == second


def test_multiple_products_at_the_same_step_are_sorted_by_name() -> None:
    products = [
        _p("Zinc Serum", ProductCategory.SERUM, TimeOfDayPreference.AM),
        _p("Alpha Serum", ProductCategory.SERUM, TimeOfDayPreference.AM),
    ]
    am, _, _ = suggest_ordering(products, RULES)
    assert [s.product_name for s in am] == ["Alpha Serum", "Zinc Serum"]
