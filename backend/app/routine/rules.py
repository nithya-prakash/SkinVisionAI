"""Loads, validates, and indexes the versioned routine rule files
(``rules/routine/ordering.json`` and ``overlap.json``).

Same policy as the ingredient engine (``app.ingredients.rules``): pure,
deterministic, offline file I/O + Pydantic validation, no network/LLM
calls, and a malformed file fails loudly rather than being silently
skipped.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pydantic

from app.core.rule_loading import RuleLoadError, read_json_rule_file
from app.routine.models import OrderingFile, OverlapFile
from app.schemas.common import ProductCategory
from app.schemas.ingredient import IngredientCategory

DEFAULT_ROUTINE_RULES_DIR = Path(__file__).resolve().parent.parent.parent / "rules" / "routine"

__all__ = [
    "DEFAULT_ROUTINE_RULES_DIR",
    "RoutineRuleSet",
    "RuleLoadError",
    "get_routine_rule_set",
    "load_routine_rule_set",
]


class RoutineRuleSet:
    """A fully loaded, validated routine rule set. Immutable after
    construction; safe to share as a process-wide singleton.
    """

    def __init__(
        self,
        am_step_order: dict[ProductCategory, int],
        pm_step_order: dict[ProductCategory, int],
        ordering_source: str,
        ordering_source_url: str,
        ordering_last_verified,
        ordering_reason: str,
        active_categories: frozenset[IngredientCategory],
        overlap_message: str,
        overlap_reason: str,
        overlap_source: str,
        overlap_source_url: str,
        overlap_last_verified,
    ) -> None:
        self.am_step_order = am_step_order
        self.pm_step_order = pm_step_order
        self.ordering_source = ordering_source
        self.ordering_source_url = ordering_source_url
        self.ordering_last_verified = ordering_last_verified
        self.ordering_reason = ordering_reason
        self.active_categories = active_categories
        self.overlap_message = overlap_message
        self.overlap_reason = overlap_reason
        self.overlap_source = overlap_source
        self.overlap_source_url = overlap_source_url
        self.overlap_last_verified = overlap_last_verified


def _index_steps(
    entries: list, *, file_label: str
) -> dict[ProductCategory, int]:
    step_order: dict[ProductCategory, int] = {}
    for entry in entries:
        if entry.category in step_order:
            raise RuleLoadError(
                f"Duplicate category {entry.category.value!r} in {file_label}"
            )
        step_order[entry.category] = entry.step_order
    return step_order


def load_routine_rule_set(rules_dir: Path) -> RoutineRuleSet:
    """Load, validate, and index the routine rule files in ``rules_dir``.

    Not cached -- callers that want a process-wide singleton should use
    ``get_routine_rule_set()``. Exposed separately so tests can point at a
    temporary directory of deliberately malformed files.
    """
    ordering_raw = read_json_rule_file(rules_dir / "ordering.json")
    overlap_raw = read_json_rule_file(rules_dir / "overlap.json")

    try:
        ordering_file = OrderingFile.model_validate(ordering_raw)
        overlap_file = OverlapFile.model_validate(overlap_raw)
    except pydantic.ValidationError as exc:
        raise RuleLoadError(f"Rule file failed schema validation: {exc}") from exc

    am_step_order = _index_steps(ordering_file.am_steps, file_label="ordering.json am_steps")
    pm_step_order = _index_steps(ordering_file.pm_steps, file_label="ordering.json pm_steps")

    if len(set(overlap_file.active_categories)) != len(overlap_file.active_categories):
        raise RuleLoadError("Duplicate category in overlap.json active_categories")
    if not overlap_file.active_categories:
        raise RuleLoadError("overlap.json active_categories must not be empty")

    return RoutineRuleSet(
        am_step_order=am_step_order,
        pm_step_order=pm_step_order,
        ordering_source=ordering_file.source,
        ordering_source_url=ordering_file.source_url,
        ordering_last_verified=ordering_file.last_verified,
        ordering_reason=ordering_file.reason,
        active_categories=frozenset(overlap_file.active_categories),
        overlap_message=overlap_file.message,
        overlap_reason=overlap_file.reason,
        overlap_source=overlap_file.source,
        overlap_source_url=overlap_file.source_url,
        overlap_last_verified=overlap_file.last_verified,
    )


@lru_cache(maxsize=1)
def get_routine_rule_set() -> RoutineRuleSet:
    """Return the process-wide, cached, validated default routine rule set."""
    return load_routine_rule_set(DEFAULT_ROUTINE_RULES_DIR)
