"""Visible shine / apparent oiliness estimation.

Method: fraction of region-of-interest pixels that are both very bright
(HSV V channel) and low-saturation (HSV S channel) -- the classic
signature of a specular highlight (a small, near-white reflection of a
light source), which is what "visible shine" looks like in a photo. This
is extremely sensitive to lighting setup and angle: a single strong light
source produces highlights regardless of the surface, and diffuse lighting
suppresses them regardless of the surface. It measures apparent shine in
this photo, not oil production.
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.vision._numeric import score_to_level
from app.vision.features import FeatureScore

METHOD = "hsv_specular_highlight_fraction"


class ShineThresholds(BaseModel):
    """Configurable shine thresholds. See docs/vision.md for rationale."""

    model_config = ConfigDict(extra="forbid")

    brightness_min: float
    saturation_max: float
    mild_min: float
    moderate_min: float
    pronounced_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "ShineThresholds":
        return cls(
            brightness_min=settings.vision_shine_brightness_min,
            saturation_max=settings.vision_shine_saturation_max,
            mild_min=settings.vision_shine_mild_min,
            moderate_min=settings.vision_shine_moderate_min,
            pronounced_min=settings.vision_shine_pronounced_min,
        )


def analyze_shine(roi_bgr: np.ndarray, thresholds: ShineThresholds) -> FeatureScore:
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].astype(np.float64)
    value = hsv[:, :, 2].astype(np.float64)

    highlight_mask = (value >= thresholds.brightness_min) & (saturation <= thresholds.saturation_max)
    fraction = float(highlight_mask.mean())

    # Already a natural 0-1 fraction; no separate normalization constant.
    score = fraction
    level = score_to_level(
        score, thresholds.mild_min, thresholds.moderate_min, thresholds.pronounced_min
    )

    return FeatureScore(
        score=round(score, 4),
        level=level,
        method=METHOD,
        note="Highly dependent on lighting setup and angle; a single strong light source increases this regardless of skin.",
    )
