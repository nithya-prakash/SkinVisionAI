"""Tests for app.vision.shine."""
from __future__ import annotations

import numpy as np

from app.schemas.vision import ObservationLevel
from app.vision.shine import ShineThresholds, analyze_shine

THRESHOLDS = ShineThresholds(
    brightness_min=220.0, saturation_max=60.0, mild_min=0.02, moderate_min=0.06, pronounced_min=0.12
)


def test_matte_mid_tone_scores_zero() -> None:
    roi = np.full((200, 200, 3), (130, 120, 115), dtype=np.uint8)
    result = analyze_shine(roi, THRESHOLDS)
    assert result.score == 0.0
    assert result.level == ObservationLevel.MINIMAL


def test_bright_low_saturation_patch_increases_score() -> None:
    roi = np.full((200, 200, 3), (130, 120, 115), dtype=np.uint8)
    roi[80:120, 80:120] = (250, 248, 250)  # bright, near-white highlight patch

    result = analyze_shine(roi, THRESHOLDS)

    # Patch is 40x40 = 1600px out of 40000px total = 4% -> above mild_min (2%).
    assert result.score > 0.0
    assert result.level != ObservationLevel.MINIMAL


def test_bright_but_saturated_color_is_not_counted_as_shine() -> None:
    """A vivid, fully saturated bright color (e.g. pure blue) is not a
    specular highlight even though its V channel is high.
    """
    roi = np.full((200, 200, 3), (255, 0, 0), dtype=np.uint8)  # pure blue in BGR
    result = analyze_shine(roi, THRESHOLDS)
    assert result.score == 0.0


def test_shine_is_deterministic() -> None:
    roi = np.full((200, 200, 3), (130, 120, 115), dtype=np.uint8)
    roi[80:120, 80:120] = (250, 248, 250)
    first = analyze_shine(roi, THRESHOLDS)
    second = analyze_shine(roi, THRESHOLDS)
    assert first.score == second.score


def test_shine_method_is_reported() -> None:
    roi = np.full((100, 100, 3), (130, 120, 115), dtype=np.uint8)
    result = analyze_shine(roi, THRESHOLDS)
    assert result.method == "hsv_specular_highlight_fraction"
