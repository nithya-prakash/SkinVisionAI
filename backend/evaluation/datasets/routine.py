"""Routine evaluation fixtures (Phase 11).

Ground truth is the production routine engine's own versioned rule files
(``rules/routine/{overlap,ordering}.json``) plus the Phase 4 compatibility
rule set it reuses -- no new routine rules are added for evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutineProduct:
    product_name: str
    raw_ingredients: str
    category: str | None = None
    time_of_day: str = "unspecified"


@dataclass(frozen=True)
class RoutineCase:
    case_id: str
    description: str
    products: tuple[RoutineProduct, ...]
    expect_overlap_ingredients: frozenset[str] = frozenset()
    expect_interaction_rule_ids: frozenset[str] = frozenset()
    expect_am_order: tuple[str, ...] = ()  # exact product_name order; empty tuple = not checked
    expect_pm_order: tuple[str, ...] = ()
    expect_unscheduled: frozenset[str] = frozenset()


ROUTINE_CASES: tuple[RoutineCase, ...] = (
    RoutineCase(
        "routine_duplicate_active_category_overlap",
        "Two products both containing retinol are flagged as an overlapping active",
        products=(
            RoutineProduct("Night Cream A", "Water, Retinol, Glycerin", "moisturizer"),
            RoutineProduct("Night Serum B", "Water, Retinol", "serum"),
        ),
        expect_overlap_ingredients=frozenset({"retinol"}),
    ),
    RoutineCase(
        "routine_retinoid_acid_overlap_produces_known_interaction",
        "A retinoid product and an AHA product across the routine produce the documented caution rule",
        products=(
            RoutineProduct("Retinol Serum", "Water, Retinol", "serum"),
            RoutineProduct("Glycolic Toner", "Water, Glycolic Acid", "toner"),
        ),
        expect_interaction_rule_ids=frozenset({"retinol_glycolic_acid_caution"}),
    ),
    RoutineCase(
        "routine_vitamin_c_overlap_across_products",
        "Two products both containing ascorbic acid are flagged as an overlapping active",
        products=(
            RoutineProduct("Brightening Serum", "Water, Ascorbic Acid", "serum"),
            RoutineProduct("Vitamin C Moisturizer", "Water, Ascorbic Acid, Glycerin", "moisturizer"),
        ),
        expect_overlap_ingredients=frozenset({"ascorbic_acid"}),
    ),
    RoutineCase(
        "routine_am_ordering_is_deterministic",
        "Cleanser, serum, and moisturizer with AM preference are placed in the documented step order",
        products=(
            RoutineProduct("Gentle Cleanser", "Water, Glycerin", "cleanser", "AM"),
            RoutineProduct("Vitamin Serum", "Water, Niacinamide", "serum", "AM"),
            RoutineProduct("Day Moisturizer", "Water, Glycerin, Dimethicone", "moisturizer", "AM"),
        ),
        expect_am_order=("Gentle Cleanser", "Vitamin Serum", "Day Moisturizer"),
    ),
    RoutineCase(
        "routine_pm_ordering_is_deterministic",
        "Cleanser, treatment, and moisturizer with PM preference are placed in the documented step order",
        products=(
            RoutineProduct("Gentle Cleanser", "Water, Glycerin", "cleanser", "PM"),
            RoutineProduct("Retinol Treatment", "Water, Retinol", "treatment", "PM"),
            RoutineProduct("Night Moisturizer", "Water, Ceramide NP", "moisturizer", "PM"),
        ),
        expect_pm_order=("Gentle Cleanser", "Retinol Treatment", "Night Moisturizer"),
    ),
    RoutineCase(
        "routine_sunscreen_defaults_to_am_even_when_unspecified",
        "A sunscreen product with no stated time-of-day is still placed in the AM sequence (the one documented exception)",
        products=(RoutineProduct("Daily SPF", "Water, Zinc Oxide", "sunscreen", "unspecified"),),
        expect_am_order=("Daily SPF",),
    ),
    RoutineCase(
        "routine_sunscreen_requested_for_pm_is_unscheduled_not_fabricated",
        "A sunscreen product explicitly requested for PM has no PM ordering rule and is correctly left unscheduled, never given a fabricated position",
        products=(RoutineProduct("Daily SPF", "Water, Zinc Oxide", "sunscreen", "PM"),),
        expect_unscheduled=frozenset({"Daily SPF"}),
    ),
    RoutineCase(
        "routine_unknown_category_is_unscheduled",
        "A product with no category is unscheduled with an explicit reason, never a guessed position",
        products=(RoutineProduct("Mystery Product", "Water, Glycerin", None, "AM"),),
        expect_unscheduled=frozenset({"Mystery Product"}),
    ),
    RoutineCase(
        "routine_unspecified_time_is_unscheduled",
        "A non-sunscreen product with unspecified time-of-day is unscheduled, never defaulted into AM or PM",
        products=(RoutineProduct("Vitamin Serum", "Water, Niacinamide", "serum", "unspecified"),),
        expect_unscheduled=frozenset({"Vitamin Serum"}),
    ),
)


# One reusable multi-product routine for the determinism check.
DETERMINISM_CASE_PRODUCTS: tuple[RoutineProduct, ...] = (
    RoutineProduct("Gentle Cleanser", "Water, Glycerin", "cleanser", "AM_AND_PM"),
    RoutineProduct("Retinol Serum", "Water, Retinol", "serum", "PM"),
    RoutineProduct("Glycolic Toner", "Water, Glycolic Acid", "toner", "AM"),
    RoutineProduct("Daily SPF", "Water, Zinc Oxide", "sunscreen", "unspecified"),
)
