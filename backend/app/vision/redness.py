"""Visible redness estimation.

Method: mean of the Lab color space's a* channel (green-red axis; positive
values trend red/magenta) across the region of interest. This is a
standard, transparent color-space technique -- not a learned model -- and
reports only a visual signal, never a skin-condition diagnosis. Redness
readings are highly sensitive to lighting (warm light inflates them, cool
light suppresses them) and to camera white-balance/color processing.

IMPORTANT FAIRNESS LIMITATION: this measures absolute warmth in the image,
not redness relative to a person's own baseline skin tone. It is not
tone-corrected, so it should not be assumed to behave identically across
all skin tones -- a naturally warmer-toned face can register a nonzero
baseline "redness" score with no visible irritation at all. This is a
known limitation of the method, not a bug; see docs/vision.md.
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.vision._numeric import clip01, score_to_level
from app.vision.features import FeatureScore

METHOD = "lab_a_channel_mean"

# OpenCV's Lab a* channel is stored 0-255 with 128 as the neutral midpoint
# (unlike the CIE-standard -128..127 range) -- subtract 128 to get a
# signed "how far toward red" value before normalizing.
_LAB_A_NEUTRAL = 128.0


class RednessThresholds(BaseModel):
    """Configurable redness thresholds. See docs/vision.md for rationale."""

    model_config = ConfigDict(extra="forbid")

    norm_max: float
    mild_min: float
    moderate_min: float
    pronounced_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RednessThresholds":
        return cls(
            norm_max=settings.vision_redness_norm_max,
            mild_min=settings.vision_redness_mild_min,
            moderate_min=settings.vision_redness_moderate_min,
            pronounced_min=settings.vision_redness_pronounced_min,
        )


def analyze_redness(roi_bgr: np.ndarray, thresholds: RednessThresholds) -> FeatureScore:
    lab = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2LAB)
    a_channel = lab[:, :, 1].astype(np.float64) - _LAB_A_NEUTRAL
    mean_a = float(a_channel.mean())

    score = clip01(max(mean_a, 0.0) / thresholds.norm_max)
    level = score_to_level(
        score, thresholds.mild_min, thresholds.moderate_min, thresholds.pronounced_min
    )

    return FeatureScore(
        score=round(score, 4),
        level=level,
        method=METHOD,
        note=(
            "Estimated from color analysis, not tone-corrected; lighting, white "
            "balance, and a person's baseline skin tone all affect this measurement."
        ),
    )
