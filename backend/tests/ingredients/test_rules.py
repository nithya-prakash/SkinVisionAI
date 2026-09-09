"""Tests for app.ingredients.rules: loading, schema validation, and
cross-file consistency checks. Malformed rule files must fail loudly
(raise RuleLoadError) rather than silently skipping bad entries.

Also verifies the real, shipped default rule set loads successfully and
that rule loading requires no network access.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingredients.rules import DEFAULT_RULES_DIR, RuleLoadError, get_rule_set, load_rule_set

VALID_ALIASES = {
    "version": "1.0.0",
    "last_updated": "2026-01-01",
    "ingredients": [
        {"canonical_name": "water", "aliases": ["aqua"]},
        {"canonical_name": "retinol", "aliases": []},
        {"canonical_name": "glycolic_acid", "aliases": []},
    ],
    "ambiguous_aliases": {"vitamin a": ["retinol", "glycolic_acid"]},
}
VALID_CATEGORIES = {
    "version": "1.0.0",
    "categories": {"retinoid": ["retinol"], "aha": ["glycolic_acid"]},
}
VALID_COMPATIBILITY = {
    "version": "1.0.0",
    "last_updated": "2026-01-01",
    "rules": [
        {
            "rule_id": "retinol_glycolic_acid_caution",
            "ingredient_a": "retinol",
            "ingredient_b": "glycolic_acid",
            "severity": "caution",
            "message": "May increase irritation.",
            "reason": "Both can irritate skin on their own.",
            "source": "Test Source",
            "source_url": "https://example.org/retinol",
            "last_verified": "2026-01-01",
        }
    ],
}


def _write_rules_dir(tmp_path: Path, *, aliases=None, categories=None, compatibility=None) -> Path:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "aliases.json").write_text(json.dumps(aliases if aliases is not None else VALID_ALIASES))
    (rules_dir / "categories.json").write_text(
        json.dumps(categories if categories is not None else VALID_CATEGORIES)
    )
    (rules_dir / "compatibility.json").write_text(
        json.dumps(compatibility if compatibility is not None else VALID_COMPATIBILITY)
    )
    return rules_dir


# --- Happy path ---


def test_valid_rule_set_loads_successfully(tmp_path: Path) -> None:
    rule_set = load_rule_set(_write_rules_dir(tmp_path))
    assert "retinol" in rule_set.canonical_names
    assert rule_set.alias_index["aqua"] == "water"
    assert rule_set.find_rule("retinol", "glycolic_acid") is not None


def test_find_rule_matches_reverse_order(tmp_path: Path) -> None:
    rule_set = load_rule_set(_write_rules_dir(tmp_path))
    forward = rule_set.find_rule("retinol", "glycolic_acid")
    reverse = rule_set.find_rule("glycolic_acid", "retinol")
    assert forward is reverse
    assert forward.rule_id == "retinol_glycolic_acid_caution"


def test_default_shipped_rule_set_loads_successfully() -> None:
    """The real rule set this project ships must itself load cleanly."""
    rule_set = load_rule_set(DEFAULT_RULES_DIR)
    assert len(rule_set.canonical_names) > 0
    assert len(rule_set.rules_by_pair) > 0


def test_get_rule_set_is_cached_singleton() -> None:
    assert get_rule_set() is get_rule_set()


# --- Malformed files ---


def test_malformed_json_raises(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "aliases.json").write_text("{not valid json")
    (rules_dir / "categories.json").write_text(json.dumps(VALID_CATEGORIES))
    (rules_dir / "compatibility.json").write_text(json.dumps(VALID_COMPATIBILITY))
    with pytest.raises(RuleLoadError, match="Malformed JSON"):
        load_rule_set(rules_dir)


def test_missing_rule_file_raises(tmp_path: Path) -> None:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "aliases.json").write_text(json.dumps(VALID_ALIASES))
    (rules_dir / "categories.json").write_text(json.dumps(VALID_CATEGORIES))
    # compatibility.json intentionally missing
    with pytest.raises(RuleLoadError, match="not found"):
        load_rule_set(rules_dir)


def test_schema_violation_raises(tmp_path: Path) -> None:
    bad_aliases = {**VALID_ALIASES, "ingredients": "not a list"}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_duplicate_canonical_name_raises(tmp_path: Path) -> None:
    bad_aliases = {
        **VALID_ALIASES,
        "ingredients": [
            {"canonical_name": "retinol", "aliases": []},
            {"canonical_name": "retinol", "aliases": ["duplicate"]},
        ],
    }
    with pytest.raises(RuleLoadError, match="Duplicate canonical_name"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_alias_colliding_across_two_ingredients_raises(tmp_path: Path) -> None:
    bad_aliases = {
        **VALID_ALIASES,
        "ingredients": [
            {"canonical_name": "retinol", "aliases": ["shared alias"]},
            {"canonical_name": "glycolic_acid", "aliases": ["shared alias"]},
        ],
    }
    with pytest.raises(RuleLoadError, match="maps to multiple canonical ingredients"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_ambiguous_alias_with_only_one_candidate_raises(tmp_path: Path) -> None:
    bad_aliases = {**VALID_ALIASES, "ambiguous_aliases": {"vitamin a": ["retinol"]}}
    with pytest.raises(RuleLoadError, match="at least two candidates"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_ambiguous_alias_referencing_unknown_ingredient_raises(tmp_path: Path) -> None:
    bad_aliases = {
        **VALID_ALIASES,
        "ambiguous_aliases": {"vitamin a": ["retinol", "totally_unknown_ingredient"]},
    }
    with pytest.raises(RuleLoadError, match="unknown canonical ingredient"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_ambiguous_alias_duplicated_as_direct_alias_raises(tmp_path: Path) -> None:
    bad_aliases = {
        **VALID_ALIASES,
        "ingredients": [
            {"canonical_name": "retinol", "aliases": ["vitamin a"]},
            {"canonical_name": "glycolic_acid", "aliases": []},
        ],
        "ambiguous_aliases": {"vitamin a": ["retinol", "glycolic_acid"]},
    }
    with pytest.raises(RuleLoadError, match="both.*a direct alias.*ambiguous"):
        load_rule_set(_write_rules_dir(tmp_path, aliases=bad_aliases))


def test_category_referencing_unknown_ingredient_raises(tmp_path: Path) -> None:
    bad_categories = {"version": "1.0.0", "categories": {"retinoid": ["totally_unknown_ingredient"]}}
    with pytest.raises(RuleLoadError, match="unknown canonical ingredient"):
        load_rule_set(_write_rules_dir(tmp_path, categories=bad_categories))


def test_duplicate_rule_id_raises(tmp_path: Path) -> None:
    bad_compat = {
        **VALID_COMPATIBILITY,
        "rules": VALID_COMPATIBILITY["rules"] * 2,
    }
    with pytest.raises(RuleLoadError, match="Duplicate rule_id"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_duplicate_pair_with_different_rule_id_raises(tmp_path: Path) -> None:
    second_rule = {**VALID_COMPATIBILITY["rules"][0], "rule_id": "a_different_id"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [VALID_COMPATIBILITY["rules"][0], second_rule]}
    with pytest.raises(RuleLoadError, match="duplicates an existing rule"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_rule_referencing_unknown_ingredient_raises(tmp_path: Path) -> None:
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "ingredient_b": "totally_unknown_ingredient"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="unknown canonical ingredient"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_rule_with_identical_ingredients_raises(tmp_path: Path) -> None:
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "ingredient_b": "retinol"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="identical ingredient_a and ingredient_b"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_missing_source_raises(tmp_path: Path) -> None:
    bad_rule = dict(VALID_COMPATIBILITY["rules"][0])
    del bad_rule["source"]
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_missing_source_url_raises(tmp_path: Path) -> None:
    bad_rule = dict(VALID_COMPATIBILITY["rules"][0])
    del bad_rule["source_url"]
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_non_http_source_url_raises(tmp_path: Path) -> None:
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "source_url": "not-a-url"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_unsupported_severity_raises(tmp_path: Path) -> None:
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "severity": "extremely_dangerous"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_no_known_conflict_severity_rejected_in_rule_file(tmp_path: Path) -> None:
    """no_known_conflict is produced dynamically only -- never authored."""
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "severity": "no_known_conflict"}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))


def test_extra_field_in_rule_rejected(tmp_path: Path) -> None:
    bad_rule = {**VALID_COMPATIBILITY["rules"][0], "confidence_percent": 99}
    bad_compat = {**VALID_COMPATIBILITY, "rules": [bad_rule]}
    with pytest.raises(RuleLoadError, match="failed schema validation"):
        load_rule_set(_write_rules_dir(tmp_path, compatibility=bad_compat))
