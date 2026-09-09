"""Loads, validates, and indexes the versioned ingredient rule files.

Everything here is pure, deterministic, offline file I/O + Pydantic
validation -- no network calls, no LLM calls, no randomness. A malformed
rule file fails loudly (raises ``RuleLoadError``) rather than silently
skipping bad entries: unsupported or unverifiable rules must never enter
the system quietly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pydantic

from app.core.rule_loading import RuleLoadError, read_json_rule_file
from app.ingredients.models import AliasesFile, CategoriesFile, CompatibilityFile, CompatibilityRule
from app.schemas.ingredient import IngredientCategory

DEFAULT_RULES_DIR = Path(__file__).resolve().parent.parent.parent / "rules" / "ingredients"

__all__ = ["DEFAULT_RULES_DIR", "IngredientRuleSet", "RuleLoadError", "get_rule_set", "load_rule_set"]


def _casefold(text: str) -> str:
    return " ".join(text.split()).casefold()


class IngredientRuleSet:
    """A fully loaded, validated, and cross-indexed rule set. Immutable
    after construction; safe to share as a process-wide singleton.
    """

    def __init__(
        self,
        canonical_names: frozenset[str],
        alias_index: dict[str, str],
        ambiguous_aliases: dict[str, list[str]],
        ingredient_categories: dict[str, list[IngredientCategory]],
        rules_by_pair: dict[tuple[str, str], CompatibilityRule],
    ) -> None:
        self.canonical_names = canonical_names
        self.alias_index = alias_index
        self.ambiguous_aliases = ambiguous_aliases
        self.ingredient_categories = ingredient_categories
        self.rules_by_pair = rules_by_pair

    def lookup(self, casefolded_token: str) -> tuple[str | None, bool]:
        """Resolve an already-casefolded, whitespace-normalized token.

        Returns ``(canonical_name_or_None, is_ambiguous)``. A canonical
        name is only ever a name this rule set actually defines -- an
        unrecognized token always resolves to ``(None, False)``, never a
        guess.
        """
        if casefolded_token in self.canonical_names:
            return casefolded_token, False
        if casefolded_token in self.ambiguous_aliases:
            return None, True
        if casefolded_token in self.alias_index:
            return self.alias_index[casefolded_token], False
        return None, False

    def find_rule(self, ingredient_a: str, ingredient_b: str) -> CompatibilityRule | None:
        """Look up a rule for a pair of canonical names, in either order."""
        return self.rules_by_pair.get((ingredient_a, ingredient_b)) or self.rules_by_pair.get(
            (ingredient_b, ingredient_a)
        )


def _validate_and_index(
    aliases_file: AliasesFile,
    categories_file: CategoriesFile,
    compatibility_file: CompatibilityFile,
) -> IngredientRuleSet:
    canonical_names: set[str] = set()
    for entry in aliases_file.ingredients:
        if entry.canonical_name in canonical_names:
            raise RuleLoadError(
                f"Duplicate canonical_name in aliases.json: {entry.canonical_name!r}"
            )
        canonical_names.add(entry.canonical_name)

    alias_index: dict[str, str] = {}
    for entry in aliases_file.ingredients:
        for alias in entry.aliases:
            key = _casefold(alias)
            if not key:
                raise RuleLoadError(
                    f"Empty alias for canonical ingredient {entry.canonical_name!r}"
                )
            if key in canonical_names and key != entry.canonical_name:
                raise RuleLoadError(
                    f"Alias {alias!r} collides with a different canonical ingredient name"
                )
            if key in alias_index and alias_index[key] != entry.canonical_name:
                raise RuleLoadError(
                    f"Alias {alias!r} maps to multiple canonical ingredients "
                    f"({alias_index[key]!r} and {entry.canonical_name!r}) -- use "
                    "ambiguous_aliases instead of two conflicting direct aliases"
                )
            alias_index[key] = entry.canonical_name

    # Canonical names are stored snake_case (e.g. "glycolic_acid") as a
    # Python-identifier-style key, but no real ingredient list is ever
    # written that way -- INCI text always uses natural spacing ("Glycolic
    # Acid"). Without this, only single-word canonical names (retinol,
    # niacinamide, water) would ever match; every multi-word one would
    # silently fail to normalize. Register the space-separated form as an
    # implicit alias for every multi-word canonical name.
    for name in canonical_names:
        if "_" not in name:
            continue
        spaced = name.replace("_", " ")
        if spaced in alias_index and alias_index[spaced] != name:
            raise RuleLoadError(
                f"Implicit spaced form {spaced!r} of canonical name {name!r} "
                f"collides with an existing alias for {alias_index[spaced]!r}"
            )
        alias_index.setdefault(spaced, name)

    ambiguous_aliases: dict[str, list[str]] = {}
    for raw_alias, candidates in aliases_file.ambiguous_aliases.items():
        key = _casefold(raw_alias)
        if key in alias_index:
            raise RuleLoadError(
                f"{raw_alias!r} is listed both as a direct alias and as ambiguous"
            )
        if key in canonical_names:
            raise RuleLoadError(
                f"{raw_alias!r} is listed as ambiguous but is itself a canonical ingredient name"
            )
        if len(candidates) < 2:
            raise RuleLoadError(
                f"Ambiguous alias {raw_alias!r} must list at least two candidates"
            )
        unknown_candidates = [c for c in candidates if c not in canonical_names]
        if unknown_candidates:
            raise RuleLoadError(
                f"Ambiguous alias {raw_alias!r} references unknown canonical "
                f"ingredient(s): {unknown_candidates}"
            )
        ambiguous_aliases[key] = list(candidates)

    ingredient_categories: dict[str, list[IngredientCategory]] = {
        name: [] for name in canonical_names
    }
    for category, members in categories_file.categories.items():
        for member in members:
            if member not in canonical_names:
                raise RuleLoadError(
                    f"categories.json references unknown canonical ingredient "
                    f"{member!r} under category {category.value!r}"
                )
            ingredient_categories[member].append(category)

    rules_by_pair: dict[tuple[str, str], CompatibilityRule] = {}
    seen_rule_ids: set[str] = set()
    for rule in compatibility_file.rules:
        if rule.rule_id in seen_rule_ids:
            raise RuleLoadError(f"Duplicate rule_id in compatibility.json: {rule.rule_id!r}")
        seen_rule_ids.add(rule.rule_id)

        for name in (rule.ingredient_a, rule.ingredient_b):
            if name not in canonical_names:
                raise RuleLoadError(
                    f"Rule {rule.rule_id!r} references unknown canonical "
                    f"ingredient {name!r} -- add it to aliases.json first"
                )
        if rule.ingredient_a == rule.ingredient_b:
            raise RuleLoadError(
                f"Rule {rule.rule_id!r} has identical ingredient_a and ingredient_b"
            )

        pair_key = (rule.ingredient_a, rule.ingredient_b)
        reverse_key = (rule.ingredient_b, rule.ingredient_a)
        if pair_key in rules_by_pair or reverse_key in rules_by_pair:
            raise RuleLoadError(
                f"Rule {rule.rule_id!r} duplicates an existing rule for the same "
                "ingredient pair (rules are symmetric -- only one rule per pair "
                "is allowed)"
            )
        rules_by_pair[pair_key] = rule

    return IngredientRuleSet(
        canonical_names=frozenset(canonical_names),
        alias_index=alias_index,
        ambiguous_aliases=ambiguous_aliases,
        ingredient_categories=ingredient_categories,
        rules_by_pair=rules_by_pair,
    )


def load_rule_set(rules_dir: Path) -> IngredientRuleSet:
    """Load, validate, and index the rule files in ``rules_dir``.

    Not cached -- callers that want a process-wide singleton should use
    ``get_rule_set()``. Exposed separately so tests can point at a
    temporary directory of deliberately malformed files without touching
    any cache.
    """
    aliases_raw = read_json_rule_file(rules_dir / "aliases.json")
    categories_raw = read_json_rule_file(rules_dir / "categories.json")
    compatibility_raw = read_json_rule_file(rules_dir / "compatibility.json")

    try:
        aliases_file = AliasesFile.model_validate(aliases_raw)
        categories_file = CategoriesFile.model_validate(categories_raw)
        compatibility_file = CompatibilityFile.model_validate(compatibility_raw)
    except pydantic.ValidationError as exc:
        raise RuleLoadError(f"Rule file failed schema validation: {exc}") from exc

    return _validate_and_index(aliases_file, categories_file, compatibility_file)


@lru_cache(maxsize=1)
def get_rule_set() -> IngredientRuleSet:
    """Return the process-wide, cached, validated default rule set."""
    return load_rule_set(DEFAULT_RULES_DIR)
