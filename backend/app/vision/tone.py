"""Visible uneven-tone estimation.

Method: standard deviation of a *smoothed* copy of the Lab L* (lightness)
channel across the region of interest -- how much regional, large-scale
brightness variation exists, deliberately excluding fine-grained
pixel-level noise (that is what ``texture.py`` measures; without this
smoothing step, a noisy-but-otherwise-flat region would incorrectly score
high on both features). This is a generic color-distribution measurement,
not an assessment of pigmentation or any medical condition, and is
affected by shadows, uneven lighting across the face, and camera dynamic
range just as much as by the skin itself.
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.vision._numeric import clip01, score_to_level
from app.vision.features import FeatureScore

METHOD = "lab_l_channel_stddev_smoothed"

# Blur radius as a fraction of the region's shorter side -- large enough to
# average out per-pixel/texture-scale noise, small enough to preserve
# genuine regional (e.g. cheek-vs-forehead) tone differences.
_BLUR_FRACTION = 0.08
_MIN_KERNEL = 5


def _odd_kernel(size_px: int) -> int:
    kernel = max(_MIN_KERNEL, round(size_px * _BLUR_FRACTION))
    return kernel if kernel % 2 == 1 else kernel + 1


class ToneThresholds(BaseModel):
    """Configurable uneven-tone thresholds. See docs/vision.md for rationale."""

    model_config = ConfigDict(extra="forbid")

    norm_max: float
    mild_min: float
    moderate_min: float
    pronounced_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "ToneThresholds":
        return cls(
            norm_max=settings.vision_tone_norm_max,
            mild_min=settings.vision_tone_mild_min,
            moderate_min=settings.vision_tone_moderate_min,
            pronounced_min=settings.vision_tone_pronounced_min,
        )


def analyze_tone(roi_bgr: np.ndarray, thresholds: ToneThresholds) -> FeatureScore:
    lab = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2LAB)
    l_channel = lab[:, :, 0]

    kernel = _odd_kernel(min(l_channel.shape[:2]))
    smoothed = cv2.GaussianBlur(l_channel, (kernel, kernel), 0).astype(np.float64)
    stddev = float(smoothed.std())

    score = clip01(stddev / thresholds.norm_max)
    level = score_to_level(
        score, thresholds.mild_min, thresholds.moderate_min, thresholds.pronounced_min
    )

    return FeatureScore(
        score=round(score, 4),
        level=level,
        method=METHOD,
        note="Measures regional brightness variation, not fine texture; shadows and uneven lighting affect this as much as skin tone.",
    )
