"""Runs the vision evaluation suite as a regular pytest test -- this
*is* ``pytest tests/evaluation/`` for the vision subsystem. Fully
offline: synthetic images only, no network.
"""
from __future__ import annotations

import pytest

from evaluation.runners import vision_runner
from tests.evaluation._helpers import assert_all_passed


@pytest.fixture(scope="module")
def results():
    return vision_runner.run()


def test_vision_evaluation_suite_passes(results) -> None:
    assert_all_passed(results)


def test_vision_evaluation_has_no_duplicate_case_ids(results) -> None:
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


def test_vision_evaluation_covers_every_observable_feature(results) -> None:
    covered = {r.case_id for r in results}
    assert any("redness" in c for c in covered)
    assert any("texture" in c for c in covered)
    assert any("shine" in c for c in covered)
    assert any("uneven_tone" in c for c in covered)
    assert any("spots_marks" in c for c in covered)
    assert any("quality" in c for c in covered)


def test_vision_evaluation_includes_a_determinism_check(results) -> None:
    assert any("deterministic" in r.case_id for r in results)
