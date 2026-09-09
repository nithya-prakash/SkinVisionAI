"""Deterministic ingredient compatibility engine.

Given a raw ingredient token list, normalizes it and finds every pairwise
interaction supported by the versioned rule set. No LLM, no network, no
randomness -- the same input and rule set always produce the same output.
See docs/ingredients.md for the severity model and wording policy.
"""
from __future__ import annotations

from itertools import combinations

from app.ingredients.models import CompatibilityRule
from app.ingredients.normalizer import normalize_ingredient, normalize_ingredient_list
from app.ingredients.rules import IngredientRuleSet, get_rule_set
from app.schemas.ingredient import (
    CompatibilityResult,
    IngredientInteraction,
    NormalizedIngredient,
    RuleSeverity,
)

GENERAL_LIMITATION = (
    "Real-world tolerability can depend on concentration, formulation, pH, "
    "frequency, application timing, individual sensitivity, skin barrier "
    "condition, and the rest of your routine -- this is a simplified "
    "educational model, not a clinical assessment."
)
ABSENCE_LIMITATION = (
    "The absence of a listed interaction does not mean a combination is "
    "proven safe -- it means no rule exists in this system's small, "
    "curated rule set for that specific pair."
)
NO_KNOWN_CONFLICT_MESSAGE = "No known conflict is represented in the current rule set for this pair."
UNRECOGNIZED_MESSAGE_TEMPLATE = (
    "No supported rule is available: {tokens} not recognized in this system's rule set."
)


def _rule_to_interaction(rule: CompatibilityRule) -> IngredientInteraction:
    return IngredientInteraction(
        rule_id=rule.rule_id,
        ingredient_a=rule.ingredient_a,
        ingredient_b=rule.ingredient_b,
        severity=rule.severity,
        message=rule.message,
        reason=rule.reason,
        source=rule.source,
        source_url=rule.source_url,
        last_verified=rule.last_verified,
    )


def check_ingredient_compatibility(
    ingredient_list: list[str], rule_set: IngredientRuleSet | None = None
) -> CompatibilityResult:
    """Normalize ``ingredient_list`` (already-split raw tokens -- use
    ``app.ingredients.parser.parse_ingredient_list`` first if starting
    from a raw comma-separated string) and find every supported
    interaction among the ingredients it resolves to.

    Duplicate ingredients (by canonical name, after normalization) never
    produce duplicate interaction findings, and a rule matches regardless
    of which order its two ingredients appear in the input.
    """
    rs = rule_set or get_rule_set()
    normalized = normalize_ingredient_list(ingredient_list, rs)
    return _compatibility_from_normalized(normalized, rs)


def _compatibility_from_normalized(
    normalized: list[NormalizedIngredient], rs: IngredientRuleSet
) -> CompatibilityResult:
    matched_canonical: list[str] = []
    seen: set[str] = set()
    for ing in normalized:
        if ing.matched and ing.normalized_name and ing.normalized_name not in seen:
            seen.add(ing.normalized_name)
            matched_canonical.append(ing.normalized_name)

    interactions: list[IngredientInteraction] = []
    for a, b in combinations(sorted(matched_canonical), 2):
        rule = rs.find_rule(a, b)
        if rule is not None:
            interactions.append(_rule_to_interaction(rule))

    unknown_ingredients = [ing.raw_text for ing in normalized if not ing.matched]

    limitations = [GENERAL_LIMITATION]
    if len(matched_canonical) >= 2:
        limitations.append(ABSENCE_LIMITATION)

    return CompatibilityResult(
        ingredients=normalized,
        interactions=interactions,
        unknown_ingredients=unknown_ingredients,
        limitations=limitations,
    )


def check_pair(
    ingredient_a: str, ingredient_b: str, rule_set: IngredientRuleSet | None = None
) -> IngredientInteraction:
    """Check one specific pair, always returning a result -- including an
    explicit, honest "no known conflict represented" finding when no rule
    matches. Intended for a future agent tool ("can I use X with Y?"); the
    bulk ``check_ingredient_compatibility`` above is what
    ``POST /api/products/analyze`` uses for a whole ingredient list.
    """
    rs = rule_set or get_rule_set()
    norm_a = normalize_ingredient(ingredient_a, rs)
    norm_b = normalize_ingredient(ingredient_b, rs)

    if not norm_a.matched or not norm_b.matched:
        unresolved = [ing.raw_text for ing in (norm_a, norm_b) if not ing.matched]
        return IngredientInteraction(
            ingredient_a=norm_a.normalized_name or norm_a.raw_text,
            ingredient_b=norm_b.normalized_name or norm_b.raw_text,
            severity=RuleSeverity.NO_KNOWN_CONFLICT,
            message=UNRECOGNIZED_MESSAGE_TEMPLATE.format(tokens=", ".join(unresolved)),
        )

    assert norm_a.normalized_name is not None  # matched implies a name
    assert norm_b.normalized_name is not None
    rule = rs.find_rule(norm_a.normalized_name, norm_b.normalized_name)
    if rule is not None:
        return _rule_to_interaction(rule)

    return IngredientInteraction(
        ingredient_a=norm_a.normalized_name,
        ingredient_b=norm_b.normalized_name,
        severity=RuleSeverity.NO_KNOWN_CONFLICT,
        message=NO_KNOWN_CONFLICT_MESSAGE,
    )
