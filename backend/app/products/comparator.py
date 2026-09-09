"""Deterministic product-vs-product comparison (Phase 5).

Reuses the Phase 4 ingredient engine (parser, normalizer, compatibility)
entirely -- no ingredient rule logic is duplicated here. No LLM call, no
network call, no randomness. Deliberately produces no overall
"better product" score; see docs/ingredients.md's wording policy.
"""
from __future__ import annotations

from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.normalizer import normalize_ingredient_list
from app.ingredients.parser import parse_ingredient_list
from app.ingredients.rules import get_rule_set
from app.schemas.product import ProductCompareRequest, ProductComparisonResult

GENERAL_LIMITATION = (
    "Real-world tolerability can depend on concentration, formulation, pH, "
    "frequency, application timing, individual sensitivity, skin barrier "
    "condition, and the rest of your routine -- this is a simplified "
    "educational model, not a clinical assessment."
)


def compare_products(request: ProductCompareRequest) -> ProductComparisonResult:
    rule_set = get_rule_set()

    tokens_a = parse_ingredient_list(request.product_a.raw_ingredient_text)
    tokens_b = parse_ingredient_list(request.product_b.raw_ingredient_text)
    normalized_a = normalize_ingredient_list(tokens_a, rule_set)
    normalized_b = normalize_ingredient_list(tokens_b, rule_set)

    canonical_a = {ing.normalized_name for ing in normalized_a if ing.matched and ing.normalized_name}
    canonical_b = {ing.normalized_name for ing in normalized_b if ing.matched and ing.normalized_name}

    shared_ingredients = sorted(canonical_a & canonical_b)
    only_in_a = sorted(canonical_a - canonical_b)
    only_in_b = sorted(canonical_b - canonical_a)

    categories_a = {cat for ing in normalized_a if ing.matched for cat in ing.categories}
    categories_b = {cat for ing in normalized_b if ing.matched for cat in ing.categories}
    shared_categories = sorted(categories_a & categories_b, key=lambda c: c.value)

    # Reuse Phase 4's engine verbatim over the union of both products'
    # ingredients -- finds any interaction between A and B (or within
    # either product) without duplicating any compatibility rule logic.
    compat_result = check_ingredient_compatibility(tokens_a + tokens_b)

    unknown_a = [ing.raw_text for ing in normalized_a if not ing.matched]
    unknown_b = [ing.raw_text for ing in normalized_b if not ing.matched]

    return ProductComparisonResult(
        product_a_name=request.product_a.name,
        product_b_name=request.product_b.name,
        shared_ingredients=shared_ingredients,
        only_in_a=only_in_a,
        only_in_b=only_in_b,
        shared_categories=shared_categories,
        interactions=compat_result.interactions,
        unknown_ingredients_a=unknown_a,
        unknown_ingredients_b=unknown_b,
        limitations=[GENERAL_LIMITATION],
    )
