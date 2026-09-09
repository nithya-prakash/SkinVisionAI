"""Tests for app.vision.spots."""
from __future__ import annotations

import cv2
import numpy as np

from app.schemas.vision import ObservationLevel
from app.vision.spots import SpotsThresholds, analyze_spots

THRESHOLDS = SpotsThresholds(
    diff_threshold=18,
    min_area_px=12,
    max_area_fraction=0.02,
    norm_max_count=25,
    mild_min=0.15,
    moderate_min=0.4,
    pronounced_min=0.7,
)


def _base(size: int = 300) -> np.ndarray:
    return np.full((size, size, 3), (150, 135, 125), dtype=np.uint8)


def _with_spots(count: int, radius: int = 6, size: int = 300) -> np.ndarray:
    array = _base(size)
    rng = np.random.default_rng(7)
    margin = radius * 3
    for _ in range(count):
        cx = int(rng.integers(margin, size - margin))
        cy = int(rng.integers(margin, size - margin))
        cv2.circle(array, (cx, cy), radius, (60, 50, 45), thickness=-1)
    return array


def test_uniform_patch_has_no_spots() -> None:
    result = analyze_spots(_base(), THRESHOLDS)
    assert result.score == 0.0
    assert result.level == ObservationLevel.MINIMAL


def test_patch_with_spots_scores_higher_than_uniform() -> None:
    spotted_result = analyze_spots(_with_spots(8), THRESHOLDS)
    uniform_result = analyze_spots(_base(), THRESHOLDS)
    assert spotted_result.score > uniform_result.score
    assert spotted_result.level != ObservationLevel.MINIMAL


def test_more_spots_scores_higher() -> None:
    few = analyze_spots(_with_spots(3), THRESHOLDS)
    many = analyze_spots(_with_spots(15), THRESHOLDS)
    assert many.score >= few.score


def test_large_uniform_region_is_not_counted_as_a_spot() -> None:
    """A big block (e.g. shadow/lighting gradient) exceeding max_area_fraction
    must not be counted as a 'spot' -- that's what the area filter is for.
    """
    array = _base(300)
    array[50:250, 50:250] = (60, 50, 45)  # 200x200 block = 44% of area
    result = analyze_spots(array, THRESHOLDS)
    assert result.score == 0.0


def test_spots_is_deterministic() -> None:
    roi = _with_spots(8)
    first = analyze_spots(roi, THRESHOLDS)
    second = analyze_spots(roi, THRESHOLDS)
    assert first.score == second.score


def test_spots_method_is_reported() -> None:
    result = analyze_spots(_base(), THRESHOLDS)
    assert result.method == "highpass_blob_count"
