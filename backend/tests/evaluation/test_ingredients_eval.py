"""Runs the ingredient evaluation suite as a regular pytest test. Fully
offline: exercises the real production rule files, no network.
"""
from __future__ import annotations

import pytest

from evaluation.datasets.ingredients import COMPATIBILITY_CASES
from evaluation.runners import ingredients_runner
from tests.evaluation._helpers import assert_all_passed


@pytest.fixture(scope="module")
def results():
    return ingredients_runner.run()


def test_ingredients_evaluation_suite_passes(results) -> None:
    assert_all_passed(results)


def test_ingredients_evaluation_has_no_duplicate_case_ids(results) -> None:
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


def test_ingredients_evaluation_covers_all_six_production_rules() -> None:
    """The dataset must exercise every rule currently shipped in
    rules/ingredients/compatibility.json -- not a subset, and not an
    invented rule that doesn't exist in production.
    """
    covered_rule_ids = {c.expect_rule_id for c in COMPATIBILITY_CASES if c.expect_rule_id}
    assert covered_rule_ids == {
        "retinol_glycolic_acid_caution",
        "retinol_salicylic_acid_caution",
        "retinol_benzoyl_peroxide_caution",
        "retinol_ascorbic_acid_informational",
        "retinol_niacinamide_informational",
        "retinol_hyaluronic_acid_informational",
    }


def test_ingredients_evaluation_covers_ambiguous_and_unknown_cases(results) -> None:
    ids = {r.case_id for r in results}
    assert any("ambiguous" in c for c in ids)
    assert any("unknown" in c for c in ids)


def test_ingredients_evaluation_includes_reverse_order_check(results) -> None:
    assert any("reversed" in r.case_id for r in results)
