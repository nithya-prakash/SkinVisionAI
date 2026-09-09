"""Product-comparison evaluation fixtures (Phase 11).

Ground truth is the production comparator (app.products.comparator),
which reuses the Phase 4 ingredient engine verbatim -- no comparison
logic is re-implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComparisonProduct:
    name: str
    raw_ingredient_text: str
    category: str | None = None


@dataclass(frozen=True)
class ComparisonCase:
    """Every ``expect_*`` field is ``None`` when this case makes no claim
    about it (not checked at all) versus an explicit ``frozenset()`` when
    the case specifically asserts emptiness (e.g. "these two products
    share everything, so only_in_a must be empty") -- a bare default of
    ``frozenset()`` would conflate "don't care" with "must be empty" and
    silently stop checking the very cases meant to prove non-emptiness.
    """

    case_id: str
    description: str
    product_a: ComparisonProduct
    product_b: ComparisonProduct
    expect_shared: frozenset[str] | None = None
    expect_only_in_a: frozenset[str] | None = None
    expect_only_in_b: frozenset[str] | None = None
    expect_interaction_rule_ids: frozenset[str] | None = None
    expect_unknown_a: frozenset[str] | None = None
    expect_unknown_b: frozenset[str] | None = None


COMPARISON_CASES: tuple[ComparisonCase, ...] = (
    ComparisonCase(
        "comparison_shared_ingredients",
        "Two products sharing an ingredient report it as shared, not duplicated on both sides",
        product_a=ComparisonProduct("Product A", "Water, Niacinamide, Glycerin"),
        product_b=ComparisonProduct("Product B", "Water, Niacinamide"),
        expect_shared=frozenset({"water", "niacinamide"}),
        expect_only_in_a=frozenset({"glycerin"}),
        expect_only_in_b=frozenset(),
    ),
    ComparisonCase(
        "comparison_only_in_a_and_only_in_b",
        "Ingredients unique to each product are correctly attributed to the right side",
        product_a=ComparisonProduct("Product A", "Water, Retinol"),
        product_b=ComparisonProduct("Product B", "Water, Ascorbic Acid"),
        expect_shared=frozenset({"water"}),
        expect_only_in_a=frozenset({"retinol"}),
        expect_only_in_b=frozenset({"ascorbic_acid"}),
    ),
    ComparisonCase(
        "comparison_identical_products_share_everything",
        "Two products with identical ingredient lists share everything and have nothing unique to either side",
        product_a=ComparisonProduct("Product A", "Water, Glycerin, Niacinamide"),
        product_b=ComparisonProduct("Product B (same formula)", "Water, Glycerin, Niacinamide"),
        expect_shared=frozenset({"water", "glycerin", "niacinamide"}),
        expect_only_in_a=frozenset(),
        expect_only_in_b=frozenset(),
    ),
    ComparisonCase(
        "comparison_cross_product_interaction_detected",
        "A documented interaction between an ingredient in A and an ingredient in B is detected across the two products",
        product_a=ComparisonProduct("Retinol Serum", "Water, Retinol"),
        product_b=ComparisonProduct("Glycolic Toner", "Water, Glycolic Acid"),
        expect_shared=frozenset({"water"}),
        expect_only_in_a=frozenset({"retinol"}),
        expect_only_in_b=frozenset({"glycolic_acid"}),
        expect_interaction_rule_ids=frozenset({"retinol_glycolic_acid_caution"}),
    ),
    ComparisonCase(
        "comparison_unknown_ingredients_kept_separate_per_side",
        "Unknown ingredients are attributed to the correct product side, never silently dropped or merged",
        product_a=ComparisonProduct("Product A", "Water, Unobtainium"),
        product_b=ComparisonProduct("Product B", "Water, Mysterium"),
        expect_shared=frozenset({"water"}),
        expect_only_in_a=frozenset(),
        expect_only_in_b=frozenset(),
        expect_unknown_a=frozenset({"Unobtainium"}),
        expect_unknown_b=frozenset({"Mysterium"}),
    ),
    ComparisonCase(
        "comparison_duplicate_ingredients_within_one_product",
        "A duplicated ingredient within a single product's own list doesn't create a spurious 'only in' entry pair",
        product_a=ComparisonProduct("Product A", "Water, Retinol, Retinol"),
        product_b=ComparisonProduct("Product B", "Water"),
        expect_shared=frozenset({"water"}),
        expect_only_in_a=frozenset({"retinol"}),
        expect_only_in_b=frozenset(),
    ),
)

# For the determinism check.
DETERMINISM_CASE = COMPARISON_CASES[3]
