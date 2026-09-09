"""Structured, non-diagnostic visual observation schemas.

These describe *visible characteristics only* (e.g. "visible redness"), never
medical conditions. The Phase 3 vision pipeline must produce output that
validates against ``VisualObservation`` — an LLM or any other component may
never invent an observation shape outside this contract.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER


class ObservationFeature(StrEnum):
    """Visible skin characteristics the vision pipeline may report on.

    Deliberately non-diagnostic: these name what is visible, not a condition.
    """

    REDNESS = "redness"
    DRYNESS = "dryness"
    VISIBLE_TEXTURE = "visible_texture"
    SHINE_OILINESS = "shine_oiliness"
    UNEVEN_TONE = "uneven_tone"
    VISIBLE_SPOTS_MARKS = "visible_spots_marks"


class ObservationLevel(StrEnum):
    """Coarse severity bucket for a visual observation, not a diagnosis grade."""

    MINIMAL = "minimal"
    MILD = "mild"
    MODERATE = "moderate"
    PRONOUNCED = "pronounced"


class VisualObservation(BaseModel):
    """One non-diagnostic observation about a visible skin characteristic.

    ``score`` is a feature-specific 0-1 measurement (its exact meaning and
    computation depends on ``method`` -- see ``docs/vision.md``); ``level``
    is that score bucketed into a coarse, non-diagnostic severity label.
    ``confidence`` is a heuristic reliability estimate, not a calibrated
    probability -- see ``app.vision.features.compute_confidence``.
    """

    model_config = ConfigDict(extra="forbid")

    feature: ObservationFeature
    level: ObservationLevel
    score: float = Field(
        ge=0.0, le=1.0, description="Feature-specific measurement; see 'method'."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic reliability estimate, not a calibrated probability.",
    )
    method: str = Field(
        min_length=1, description="Identifies the algorithm that produced this score."
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Optional short, non-diagnostic clarifying note.",
    )


class RegionSource(StrEnum):
    """How the region of the image analyzed for visual observations was selected."""

    DETECTED_FACE = "detected_face"
    CENTER_CROP_FALLBACK = "center_crop_fallback"


class VisualAnalysisResult(BaseModel):
    """Full Phase 3 output for one analysis: structured, non-diagnostic
    visual observations plus the limitations that qualify them.

    This is what the future LLM/agent layer (Phase 6/7) consumes -- it
    never sees raw pixels, only this validated, typed result.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    image_id: UUID
    observations: list[VisualObservation]
    region_used: RegionSource
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    created_at: datetime
