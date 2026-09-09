"""Tests for app.vision._numeric -- shared clipping and level-bucketing."""
from __future__ import annotations

import pytest

from app.schemas.vision import ObservationLevel
from app.vision._numeric import clip01, score_to_level


@pytest.mark.parametrize(
    "value,expected", [(-5.0, 0.0), (-0.001, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (5.0, 1.0)]
)
def test_clip01(value: float, expected: float) -> None:
    assert clip01(value) == expected


THRESHOLDS = dict(mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, ObservationLevel.MINIMAL),
        (0.19999, ObservationLevel.MINIMAL),
        (0.2, ObservationLevel.MILD),
        (0.44999, ObservationLevel.MILD),
        (0.45, ObservationLevel.MODERATE),
        (0.69999, ObservationLevel.MODERATE),
        (0.7, ObservationLevel.PRONOUNCED),
        (1.0, ObservationLevel.PRONOUNCED),
    ],
)
def test_score_to_level_boundaries(score: float, expected: ObservationLevel) -> None:
    assert score_to_level(score, **THRESHOLDS) == expected
