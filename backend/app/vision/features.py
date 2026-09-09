"""Shared types for the per-feature extractors (redness.py, texture.py,
shine.py, tone.py, spots.py).

Each extractor returns a ``FeatureScore`` -- an internal, not-API-exposed
result -- which ``analyzer.py`` wraps into the public
``app.schemas.vision.VisualObservation`` (adding the feature tag and a
shared confidence value). Keeping ``FeatureScore`` separate lets each
extractor module be tested in isolation without needing to know the
enum tag or the confidence-calculation policy.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.vision import ObservationLevel
from app.vision._numeric import clip01


class FeatureScore(BaseModel):
    """One feature extractor's raw result before it becomes an observation."""

    model_config = ConfigDict(extra="forbid")

    score: float
    level: ObservationLevel
    method: str
    note: str | None = None


def compute_confidence(quality_score: float, region_is_detected_face: bool) -> float:
    """Heuristic confidence for every observation from one analysis run.

    NOT a calibrated probability -- it is a simple, documented product of
    two signals: the Phase 2 image-quality score (0-1), and a fixed
    reliability factor for how the analyzed region was chosen (a detected
    face is more likely to be the intended subject than a center-crop
    fallback). The result is floored at 0.1 so a low-quality analysis is
    never reported as literally zero-confidence.

    confidence = clip(quality_score * region_factor, 0.1, 1.0)
    region_factor = 0.9 if a face was detected, else 0.65
    """
    region_factor = 0.9 if region_is_detected_face else 0.65
    return round(max(clip01(quality_score * region_factor), 0.1), 4)
