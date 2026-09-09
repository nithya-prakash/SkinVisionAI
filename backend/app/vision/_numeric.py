"""Small numeric helpers shared across the vision package.

Kept separate (rather than duplicated per-module) so Phase 2's quality gate
and Phase 3's feature extractors use identical, tested primitives.
"""
from __future__ import annotations

from app.schemas.vision import ObservationLevel


def clip01(value: float) -> float:
    """Clamp a value to the closed interval [0, 1]."""
    return max(0.0, min(1.0, value))


def score_to_level(
    score: float, mild_min: float, moderate_min: float, pronounced_min: float
) -> ObservationLevel:
    """Bucket a 0-1 score into a coarse, non-diagnostic severity level.

    Cut points are configurable per feature (see ``app.config.Settings``)
    rather than hardcoded, so each feature's threshold reasoning lives in
    one documented place. Below ``mild_min`` is "minimal".
    """
    if score >= pronounced_min:
        return ObservationLevel.PRONOUNCED
    if score >= moderate_min:
        return ObservationLevel.MODERATE
    if score >= mild_min:
        return ObservationLevel.MILD
    return ObservationLevel.MINIMAL
