"""Runs the product-comparison evaluation suite as a regular pytest
test. Fully offline: exercises the real Phase 5 comparator, no network.
"""
from __future__ import annotations

import pytest

from evaluation.runners import comparison_runner
from tests.evaluation._helpers import assert_all_passed


@pytest.fixture(scope="module")
def results():
    return comparison_runner.run()


def test_comparison_evaluation_suite_passes(results) -> None:
    assert_all_passed(results)


def test_comparison_evaluation_has_no_duplicate_case_ids(results) -> None:
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


def test_comparison_evaluation_explicitly_checks_for_no_better_product_score(results) -> None:
    matching = [r for r in results if "better_product_score" in r.case_id]
    assert len(matching) == 1
    assert matching[0].passed
