"""Visible texture estimation.

Method: variance of the Laplacian of the grayscale region of interest --
the same well-known focus/edge-density measure used by the Phase 2 blur
check, but interpreted the other way around: here, on an already
in-focus image (the quality gate already screened out blurry ones), a
*higher* value indicates more visible fine-scale surface detail. This is
purely a measurement of local pixel-intensity variation, not a
classification of what causes it (texture, product residue, hair, fabric,
etc. all register identically) -- it must never be called "acne" or any
other condition name.
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.vision._numeric import clip01, score_to_level
from app.vision.features import FeatureScore

METHOD = "laplacian_variance"


class TextureThresholds(BaseModel):
    """Configurable texture thresholds. See docs/vision.md for rationale."""

    model_config = ConfigDict(extra="forbid")

    norm_max: float
    mild_min: float
    moderate_min: float
    pronounced_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "TextureThresholds":
        return cls(
            norm_max=settings.vision_texture_norm_max,
            mild_min=settings.vision_texture_mild_min,
            moderate_min=settings.vision_texture_moderate_min,
            pronounced_min=settings.vision_texture_pronounced_min,
        )


def analyze_texture(roi_bgr: np.ndarray, thresholds: TextureThresholds) -> FeatureScore:
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    score = clip01(variance / thresholds.norm_max)
    level = score_to_level(
        score, thresholds.mild_min, thresholds.moderate_min, thresholds.pronounced_min
    )

    return FeatureScore(
        score=round(score, 4),
        level=level,
        method=METHOD,
        note="Measures local pixel-intensity variation only; not specific to any particular cause.",
    )
