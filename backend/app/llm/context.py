"""Builds the trusted "ground truth" context for one explanation call:
the JSON-safe payload sent to the LLM, and the exact same deterministic
result's facts (rule ids, ingredient names, sources) that
``app.llm.validation`` checks the LLM's response against.

Both are derived from the *same* already-computed, already-validated
deterministic result object -- never reconstructed independently -- so
there is no way for the payload and the validation ground truth to drift
apart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.ingredient import CompatibilityResult
from app.schemas.product import ProductComparisonResult
from app.schemas.routine import RoutineAnalysisResult


@dataclass(frozen=True)
class DeterministicContext:
    """Ground truth for one explanation call."""

    payload: dict
    known_rule_ids: frozenset[str] = field(default_factory=frozenset)
    known_ingredient_names: frozenset[str] = field(default_factory=frozenset)
    known_overlap_ingredients: frozenset[str] = field(default_factory=frozenset)
    known_source_names: frozenset[str] = field(default_factory=frozenset)
    known_source_urls: frozenset[str] = field(default_factory=frozenset)


def _ingredient_names_from_normalized(normalized_ingredients: list) -> set[str]:
    return {
        ing.normalized_name
        for ing in normalized_ingredients
        if ing.matched and ing.normalized_name
    }


def build_product_context(result: CompatibilityResult) -> DeterministicContext:
    known_ingredient_names = _ingredient_names_from_normalized(result.ingredients)
    known_rule_ids = {i.rule_id for i in result.interactions if i.rule_id}
    known_source_names = {i.source for i in result.interactions if i.source}
    known_source_urls = {i.source_url for i in result.interactions if i.source_url}

    return DeterministicContext(
        payload=result.model_dump(mode="json"),
        known_rule_ids=frozenset(known_rule_ids),
        known_ingredient_names=frozenset(known_ingredient_names),
        known_source_names=frozenset(known_source_names),
        known_source_urls=frozenset(known_source_urls),
    )


def build_comparison_context(result: ProductComparisonResult) -> DeterministicContext:
    known_ingredient_names = set(result.shared_ingredients) | set(result.only_in_a) | set(
        result.only_in_b
    )
    known_rule_ids = {i.rule_id for i in result.interactions if i.rule_id}
    known_source_names = {i.source for i in result.interactions if i.source}
    known_source_urls = {i.source_url for i in result.interactions if i.source_url}

    return DeterministicContext(
        payload=result.model_dump(mode="json"),
        known_rule_ids=frozenset(known_rule_ids),
        known_ingredient_names=frozenset(known_ingredient_names),
        known_source_names=frozenset(known_source_names),
        known_source_urls=frozenset(known_source_urls),
    )


def build_routine_context(result: RoutineAnalysisResult) -> DeterministicContext:
    known_ingredient_names: set[str] = set()
    for product in result.products:
        known_ingredient_names |= _ingredient_names_from_normalized(product.normalized_ingredients)

    known_rule_ids = {i.rule_id for i in result.interactions if i.rule_id}
    known_overlap_ingredients = {o.ingredient for o in result.overlapping_actives}
    known_source_names = {i.source for i in result.interactions if i.source} | {
        o.source for o in result.overlapping_actives if o.source
    }
    known_source_urls = {i.source_url for i in result.interactions if i.source_url} | {
        o.source_url for o in result.overlapping_actives if o.source_url
    }

    return DeterministicContext(
        payload=result.model_dump(mode="json"),
        known_rule_ids=frozenset(known_rule_ids),
        known_ingredient_names=frozenset(known_ingredient_names),
        known_overlap_ingredients=frozenset(known_overlap_ingredients),
        known_source_names=frozenset(known_source_names),
        known_source_urls=frozenset(known_source_urls),
    )
