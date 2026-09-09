"""Routine analysis orchestration (Phase 5).

Ties together the Phase 4 ingredient engine (parser, normalizer,
compatibility) with overlap detection and AM/PM ordering to produce one
structured, deterministic ``RoutineAnalysisResult``. No LLM call, no
network call, no randomness -- the same input always produces the same
output.

Architecture:
    products -> ingredient parsing -> normalization -> category detection
    (all Phase 4, reused verbatim) -> cross-product compatibility analysis
    (Phase 4's engine run over the whole routine's ingredients at once) ->
    routine ordering rules -> structured RoutineAnalysisResult
"""
from __future__ import annotations

from collections import defaultdict

from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.parser import parse_ingredient_list
from app.ingredients.normalizer import normalize_ingredient_list
from app.ingredients.rules import get_rule_set
from app.routine.ordering import suggest_ordering
from app.routine.overlap import find_overlapping_actives
from app.routine.rules import RoutineRuleSet, get_routine_rule_set
from app.schemas.routine import (
    RoutineAnalysisRequest,
    RoutineAnalysisResult,
    RoutineInteraction,
    RoutineProductAnalysis,
)

GENERAL_LIMITATION = (
    "Real-world tolerability can depend on concentration, formulation, pH, "
    "frequency, application timing, individual sensitivity, skin barrier "
    "condition, and how these products are combined -- this is a "
    "simplified educational model, not a clinical assessment."
)
ORDERING_LIMITATION = (
    "Suggested routine order is a general educational guideline, not a "
    "required or medically correct order -- actual product layering can "
    "depend on formulation and manufacturer instructions."
)
ABSENCE_LIMITATION = (
    "The absence of a listed interaction does not mean a combination is "
    "proven safe -- it means no rule exists in this system's small, "
    "curated rule set for that specific pair."
)


def analyze_routine(
    request: RoutineAnalysisRequest, routine_rule_set: RoutineRuleSet | None = None
) -> RoutineAnalysisResult:
    routine_rules = routine_rule_set or get_routine_rule_set()
    ingredient_rules = get_rule_set()

    products_analysis: list[RoutineProductAnalysis] = []
    products_with_ingredients: list[tuple[str, list]] = []
    all_tokens: list[str] = []
    ingredient_to_products: dict[str, set[str]] = defaultdict(set)

    for product in request.products:
        tokens = parse_ingredient_list(product.raw_ingredients)
        normalized = normalize_ingredient_list(tokens, ingredient_rules)

        products_analysis.append(
            RoutineProductAnalysis(
                product_name=product.product_name,
                category=product.category,
                time_of_day=product.time_of_day,
                normalized_ingredients=normalized,
            )
        )
        products_with_ingredients.append((product.product_name, normalized))
        all_tokens.extend(tokens)

        for ing in normalized:
            if ing.matched and ing.normalized_name:
                ingredient_to_products[ing.normalized_name].add(product.product_name)

    # Cross-product (and within-product) compatibility: Phase 4's engine,
    # reused verbatim, run once over the union of every product's
    # ingredients. This naturally finds any interaction anywhere in the
    # routine -- whether both ingredients came from the same product or
    # different ones -- without duplicating any Phase 4 rule logic.
    compat_result = check_ingredient_compatibility(all_tokens)

    interactions = [
        RoutineInteraction(
            rule_id=interaction.rule_id,
            ingredient_a=interaction.ingredient_a,
            ingredient_b=interaction.ingredient_b,
            severity=interaction.severity,
            message=interaction.message,
            reason=interaction.reason,
            source=interaction.source,
            source_url=interaction.source_url,
            last_verified=interaction.last_verified,
            products=sorted(
                ingredient_to_products.get(interaction.ingredient_a, set())
                | ingredient_to_products.get(interaction.ingredient_b, set())
            ),
        )
        for interaction in compat_result.interactions
    ]

    overlapping_actives = find_overlapping_actives(
        products_with_ingredients, routine_rules, ingredient_rules
    )

    suggested_am, suggested_pm, unscheduled_products = suggest_ordering(
        request.products, routine_rules
    )

    limitations = [GENERAL_LIMITATION]
    if suggested_am or suggested_pm:
        limitations.append(ORDERING_LIMITATION)
    if len(ingredient_to_products) >= 2:
        limitations.append(ABSENCE_LIMITATION)

    return RoutineAnalysisResult(
        products=products_analysis,
        overlapping_actives=overlapping_actives,
        interactions=interactions,
        suggested_am=suggested_am,
        suggested_pm=suggested_pm,
        unscheduled_products=unscheduled_products,
        limitations=limitations,
    )
