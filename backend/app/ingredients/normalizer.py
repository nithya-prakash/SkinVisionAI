"""Deterministic normalization of parsed ingredient tokens against the
versioned rule set's canonical ingredient list and aliases.

Never guesses: an unrecognized token is returned with ``matched=False``,
and a recognized-but-ambiguous alias (e.g. "Vitamin A") is returned with
``ambiguous=True`` and its candidate canonical ingredients listed --
neither case invents a specific ingredient identity. No LLM or network
call is used anywhere in this module.
"""
from __future__ import annotations

from app.ingredients.rules import IngredientRuleSet
from app.schemas.ingredient import NormalizedIngredient


def _casefold(text: str) -> str:
    return " ".join(text.split()).casefold()


def normalize_ingredient(raw_text: str, rule_set: IngredientRuleSet) -> NormalizedIngredient:
    """Resolve one raw ingredient token against ``rule_set``."""
    key = _casefold(raw_text)
    canonical, ambiguous = rule_set.lookup(key)

    if ambiguous:
        return NormalizedIngredient(
            raw_text=raw_text,
            normalized_name=None,
            matched=False,
            ambiguous=True,
            candidates=sorted(rule_set.ambiguous_aliases[key]),
        )

    if canonical is None:
        return NormalizedIngredient(raw_text=raw_text, normalized_name=None, matched=False)

    return NormalizedIngredient(
        raw_text=raw_text,
        normalized_name=canonical,
        matched=True,
        categories=list(rule_set.ingredient_categories.get(canonical, [])),
    )


def normalize_ingredient_list(
    raw_tokens: list[str], rule_set: IngredientRuleSet
) -> list[NormalizedIngredient]:
    """Resolve every non-blank token in ``raw_tokens`` against ``rule_set``,
    in order.

    Blank/whitespace-only tokens are silently skipped -- they carry no
    ingredient identity to report (``NormalizedIngredient.raw_text``
    requires at least one character) and are not malformed input, just a
    no-op, consistent with ``app.ingredients.parser``'s own handling of
    empty chunks. Does not deduplicate -- every other original token is
    preserved for traceability; deduplication by canonical ingredient
    happens downstream in the compatibility engine, where it matters.
    """
    return [
        normalize_ingredient(token, rule_set) for token in raw_tokens if token and token.strip()
    ]
