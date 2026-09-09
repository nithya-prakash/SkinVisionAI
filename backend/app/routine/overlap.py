"""Duplicate/overlapping active-ingredient detection across products.

Deterministic, offline: given each input product's already-normalized
ingredient list, finds every canonical ingredient that (a) belongs to a
category the versioned rule set considers an "active" worth flagging, and
(b) appears in two or more distinct products. Duplication is never
labeled dangerous outright -- the message/reason/source are the versioned
rule set's own sourced wording, not invented here.
"""
from __future__ import annotations

from collections import defaultdict

from app.ingredients.rules import IngredientRuleSet
from app.routine.rules import RoutineRuleSet
from app.schemas.ingredient import NormalizedIngredient
from app.schemas.routine import OverlappingActive


def find_overlapping_actives(
    products_with_ingredients: list[tuple[str, list[NormalizedIngredient]]],
    routine_rules: RoutineRuleSet,
    ingredient_rules: IngredientRuleSet,
) -> list[OverlappingActive]:
    """``products_with_ingredients`` is a list of
    ``(product_name, normalized_ingredients)`` pairs. Returns one
    ``OverlappingActive`` per canonical active ingredient found in 2+
    distinct products, sorted by ingredient name for determinism.
    """
    ingredient_to_products: dict[str, set[str]] = defaultdict(set)

    for product_name, normalized in products_with_ingredients:
        seen_in_this_product: set[str] = set()
        for ing in normalized:
            if not ing.matched or not ing.normalized_name:
                continue
            if ing.normalized_name in seen_in_this_product:
                continue
            seen_in_this_product.add(ing.normalized_name)
            ingredient_to_products[ing.normalized_name].add(product_name)

    overlaps: list[OverlappingActive] = []
    for canonical in sorted(ingredient_to_products):
        product_names = ingredient_to_products[canonical]
        if len(product_names) < 2:
            continue

        categories = ingredient_rules.ingredient_categories.get(canonical, [])
        if not any(cat in routine_rules.active_categories for cat in categories):
            continue

        overlaps.append(
            OverlappingActive(
                ingredient=canonical,
                categories=categories,
                products=sorted(product_names),
                count=len(product_names),
                message=routine_rules.overlap_message,
                reason=routine_rules.overlap_reason,
                source=routine_rules.overlap_source,
                source_url=routine_rules.overlap_source_url,
                last_verified=routine_rules.overlap_last_verified,
            )
        )

    return overlaps
