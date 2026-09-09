"""Runs the routine evaluation suite as a regular pytest test. Fully
offline: exercises the real Phase 5 routine engine, no network.
"""
from __future__ import annotations

import pytest

from evaluation.runners import routine_runner
from tests.evaluation._helpers import assert_all_passed


@pytest.fixture(scope="module")
def results():
    return routine_runner.run()


def test_routine_evaluation_suite_passes(results) -> None:
    assert_all_passed(results)


def test_routine_evaluation_has_no_duplicate_case_ids(results) -> None:
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


def test_routine_evaluation_covers_ordering_overlap_and_unscheduled(results) -> None:
    ids = {r.case_id for r in results}
    assert any("ordering" in c for c in ids)
    assert any("overlap" in c for c in ids)
    assert any("unscheduled" in c or "unspecified" in c or "unknown_category" in c for c in ids)
    assert any("sunscreen" in c for c in ids)
