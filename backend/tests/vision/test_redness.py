"""Tests for app.vision.redness."""
from __future__ import annotations

import numpy as np
import pytest

from app.schemas.vision import ObservationLevel
from app.vision.redness import RednessThresholds, analyze_redness

THRESHOLDS = RednessThresholds(norm_max=12.0, mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)


def _bgr_patch(b: int, g: int, r: int, size: int = 100) -> np.ndarray:
    return np.full((size, size, 3), (b, g, r), dtype=np.uint8)


def test_neutral_gray_scores_near_zero() -> None:
    roi = _bgr_patch(128, 128, 128)
    result = analyze_redness(roi, THRESHOLDS)
    assert result.score < 0.1
    assert result.level == ObservationLevel.MINIMAL


def test_strongly_red_shifted_scores_high() -> None:
    roi = _bgr_patch(90, 90, 200)  # BGR: high R, low B/G
    result = analyze_redness(roi, THRESHOLDS)
    assert result.score > 0.5
    assert result.level in (ObservationLevel.MODERATE, ObservationLevel.PRONOUNCED)


def test_green_tinted_does_not_score_as_red() -> None:
    """Redness is the red-green axis specifically; a green shift should not
    register as redness.
    """
    roi = _bgr_patch(90, 200, 90)  # BGR: high G
    result = analyze_redness(roi, THRESHOLDS)
    assert result.score < 0.1


def test_redness_is_deterministic() -> None:
    roi = _bgr_patch(90, 90, 200)
    first = analyze_redness(roi, THRESHOLDS)
    second = analyze_redness(roi, THRESHOLDS)
    assert first.score == second.score
    assert first.level == second.level


def test_redness_method_is_reported() -> None:
    roi = _bgr_patch(128, 128, 128)
    result = analyze_redness(roi, THRESHOLDS)
    assert result.method == "lab_a_channel_mean"


@pytest.mark.parametrize("norm_max", [6.0, 12.0, 24.0])
def test_redness_score_stays_in_bounds_across_norm_max_values(norm_max: float) -> None:
    roi = _bgr_patch(90, 90, 200)
    t = RednessThresholds(norm_max=norm_max, mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)
    result = analyze_redness(roi, t)
    assert 0.0 <= result.score <= 1.0
