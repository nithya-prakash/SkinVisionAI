"""Tests for app.routine.rules: loading, schema validation, and
cross-file consistency checks. Malformed rule files must fail loudly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.rule_loading import RuleLoadError
from app.routine.rules import DEFAULT_ROUTINE_RULES_DIR, get_routine_rule_set, load_routine_rule_set

VALID_ORDERING = {
    "version": "1.0.0",
    "last_updated": "2026-01-01",
    "source": "Test Source",
    "source_url": "https://example.org/ordering",
    "last_verified": "2026-01-01",
    "reason": "Cleanser first, then treatment, then moisturizer.",
    "am_steps": [
        {"category": "cleanser", "step_order": 0},
        {"category": "treatment", "step_order": 1},
        {"category": "moisturizer", "step_order": 2},
        {"category": "sunscreen", "step_order": 3},
    ],
    "pm_steps": [
        {"category": "cleanser", "step_order": 0},
        {"category": "treatment", "step_order": 1},
        {"category": "moisturizer", "step_order": 2},
    ],
}
VALID_OVERLAP = {
    "version": "1.0.0",
    "last_updated": "2026-01-01",
    "source": "Test Source",
    "source_url": "https://example.org/overlap",
    "last_verified": "2026-01-01",
    "message": "Repeated exposure to the same active may increase irritation potential.",
    "reason": "Using multiple products with the same active increases total exposure.",
    "active_categories": ["retinoid", "aha"],
}


def _write_rules_dir(tmp_path: Path, *, ordering=None, overlap=None) -> Path:
    rules_dir = tmp_path / "routine_rules"
    rules_dir.mkdir()
    (rules_dir / "ordering.json").write_text(json.dumps(ordering if ordering is not None else VALID_ORDERING))
    (rules_dir / "overlap.json").write_text(json.dumps(overlap if overlap is not None else VALID_OVERLAP))
    return rules_dir


# --- Happy path ---


def test_valid_rule_set_loads_successfully(tmp_path: Path) -> None:
    rule_set = load_routine_rule_set(_write_rules_dir(tmp_path))
    assert rule_set.am_step_order["cleanser"] == 0
    assert rule_set.pm_step_order["treatment"] == 1
    assert "retinoid" in rule_set.active_categories


def test_default_shipped_rule_set_loads_successfully() -> None:
    """The real rule set this project ships must itself load cleanly."""
    rule_set = load_routine_rule_set(DEFAULT_ROUTINE_RULES_DIR)
    assert "cleanser" in rule_set.am_step_order
    assert "sunscreen" in rule_set.am_step_order
    assert "sunscreen" not in rule_set.pm_step_order
    assert len(rule_set.active_categories) > 0


def test_get_routine_rule_set_is_cached_singleton() -> None:
    assert get_routine_rule_set() is get_routine_rule_set()


# --- Malformed files ---


def test_missing_rule_file_raises(tmp_path: Path) -> None:
    rules_dir = tmp_path / "routine_rules"
    rules_dir.mkdir()
    (rules_dir / "ordering.json").write_text(json.dumps(VALID_ORDERING))
    with pytest.raises(RuleLoadError, match="not found"):
        load_routine_rule_set(rules_dir)


def test_malformed_json_raises(tmp_path: Path) -> None:
    rules_dir = tmp_path / "routine_rules"
    rules_dir.mkdir()
    (rules_dir / "ordering.json").write_text("{not valid json")
    (rules_dir / "overlap.json").write_text(json.dumps(VALID_OVERLAP))
    with pytest.raises(RuleLoadError, match="Malformed JSON"):
        load_routine_rule_set(rules_dir)


def test_schema_violation_raises(tmp_path: Path) -> None:
    bad_ordering = {**VALID_ORDERING, "am_steps": "not a list"}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_unknown_product_category_in_ordering_raises(tmp_path: Path) -> None:
    bad_ordering = {
        **VALID_ORDERING,
        "am_steps": [{"category": "spot_treatment_deluxe", "step_order": 0}],
    }
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_duplicate_category_in_am_steps_raises(tmp_path: Path) -> None:
    bad_ordering = {
        **VALID_ORDERING,
        "am_steps": [
            {"category": "cleanser", "step_order": 0},
            {"category": "cleanser", "step_order": 1},
        ],
    }
    with pytest.raises(RuleLoadError, match="Duplicate category"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_negative_step_order_raises(tmp_path: Path) -> None:
    bad_ordering = {**VALID_ORDERING, "am_steps": [{"category": "cleanser", "step_order": -1}]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_missing_source_raises(tmp_path: Path) -> None:
    bad_ordering = dict(VALID_ORDERING)
    del bad_ordering["source"]
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_non_http_source_url_raises(tmp_path: Path) -> None:
    bad_ordering = {**VALID_ORDERING, "source_url": "not-a-url"}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))


def test_unknown_ingredient_category_in_overlap_raises(tmp_path: Path) -> None:
    bad_overlap = {**VALID_OVERLAP, "active_categories": ["not_a_real_category"]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, overlap=bad_overlap))


def test_duplicate_active_category_raises(tmp_path: Path) -> None:
    bad_overlap = {**VALID_OVERLAP, "active_categories": ["retinoid", "retinoid"]}
    with pytest.raises(RuleLoadError, match="Duplicate category"):
        load_routine_rule_set(_write_rules_dir(tmp_path, overlap=bad_overlap))


def test_empty_active_categories_raises(tmp_path: Path) -> None:
    bad_overlap = {**VALID_OVERLAP, "active_categories": []}
    with pytest.raises(RuleLoadError, match="must not be empty"):
        load_routine_rule_set(_write_rules_dir(tmp_path, overlap=bad_overlap))


def test_extra_field_in_ordering_rejected(tmp_path: Path) -> None:
    bad_ordering = {**VALID_ORDERING, "unexpected_field": 1}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_routine_rule_set(_write_rules_dir(tmp_path, ordering=bad_ordering))
