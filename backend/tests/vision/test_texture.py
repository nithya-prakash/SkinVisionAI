"""Tests for app.vision.texture."""
from __future__ import annotations

import numpy as np

from app.schemas.vision import ObservationLevel
from app.vision.texture import TextureThresholds, analyze_texture

THRESHOLDS = TextureThresholds(norm_max=600.0, mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)


def test_uniform_patch_scores_zero() -> None:
    roi = np.full((200, 200, 3), 128, dtype=np.uint8)
    result = analyze_texture(roi, THRESHOLDS)
    assert result.score == 0.0
    assert result.level == ObservationLevel.MINIMAL


def test_noisy_patch_scores_higher_than_uniform() -> None:
    uniform = np.full((200, 200, 3), 128, dtype=np.uint8)
    rng = np.random.default_rng(11)
    noisy = np.clip(128 + rng.integers(-90, 91, size=(200, 200, 3)), 0, 255).astype(np.uint8)

    uniform_result = analyze_texture(uniform, THRESHOLDS)
    noisy_result = analyze_texture(noisy, THRESHOLDS)

    assert noisy_result.score > uniform_result.score


def test_texture_is_deterministic() -> None:
    rng = np.random.default_rng(11)
    roi = np.clip(128 + rng.integers(-90, 91, size=(150, 150, 3)), 0, 255).astype(np.uint8)
    first = analyze_texture(roi, THRESHOLDS)
    second = analyze_texture(roi, THRESHOLDS)
    assert first.score == second.score


def test_texture_method_is_reported() -> None:
    roi = np.full((100, 100, 3), 128, dtype=np.uint8)
    result = analyze_texture(roi, THRESHOLDS)
    assert result.method == "laplacian_variance"


def test_texture_score_never_exceeds_one() -> None:
    rng = np.random.default_rng(11)
    roi = np.clip(128 + rng.integers(-127, 128, size=(200, 200, 3)), 0, 255).astype(np.uint8)
    t = TextureThresholds(norm_max=1.0, mild_min=0.2, moderate_min=0.45, pronounced_min=0.7)
    result = analyze_texture(roi, t)
    assert result.score == 1.0
