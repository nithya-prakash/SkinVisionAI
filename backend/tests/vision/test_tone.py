"""Tests for app.vision.tone."""
from __future__ import annotations

import numpy as np

from app.schemas.vision import ObservationLevel
from app.vision.tone import ToneThresholds, analyze_tone

THRESHOLDS = ToneThresholds(norm_max=18.0, mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)


def test_uniform_patch_scores_near_zero() -> None:
    roi = np.full((200, 200, 3), (130, 120, 115), dtype=np.uint8)
    result = analyze_tone(roi, THRESHOLDS)
    assert result.score < 0.05
    assert result.level == ObservationLevel.MINIMAL


def test_gradient_scores_higher_than_uniform() -> None:
    uniform = np.full((200, 200, 3), (130, 120, 115), dtype=np.uint8)
    gradient = np.tile(
        np.linspace(60, 220, 200, dtype=np.uint8)[:, None, None], (1, 200, 3)
    ).astype(np.uint8)

    uniform_result = analyze_tone(uniform, THRESHOLDS)
    gradient_result = analyze_tone(gradient, THRESHOLDS)

    assert gradient_result.score > uniform_result.score
    assert gradient_result.level != ObservationLevel.MINIMAL


def test_tone_is_deterministic() -> None:
    gradient = np.tile(
        np.linspace(60, 220, 150, dtype=np.uint8)[:, None, None], (1, 150, 3)
    ).astype(np.uint8)
    first = analyze_tone(gradient, THRESHOLDS)
    second = analyze_tone(gradient, THRESHOLDS)
    assert first.score == second.score


def test_tone_method_is_reported() -> None:
    roi = np.full((100, 100, 3), (130, 120, 115), dtype=np.uint8)
    result = analyze_tone(roi, THRESHOLDS)
    assert result.method == "lab_l_channel_stddev_smoothed"
