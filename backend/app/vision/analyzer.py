"""Visual-observation pipeline orchestration (Phase 3).

Image -> preprocessing -> region-of-interest selection -> per-feature
extraction -> structured, non-diagnostic observations. Assumes the image
has already passed the Phase 2 quality gate -- that check is not repeated
here (see ``app.services.vision_service``).

Apparent dryness is deliberately *not* estimated: no defensible,
non-speculative image-only heuristic for skin hydration exists, so rather
than inventing a score, dryness is omitted from the observations and
surfaced as an explicit limitation instead.
"""
from __future__ import annotations

import cv2
from PIL import Image

from app.config import Settings
from app.schemas.vision import ObservationFeature, VisualObservation
from app.vision import preprocessing, redness, shine, spots, texture, tone
from app.vision.features import compute_confidence
from app.vision.region import RegionResult, RegionSource, RegionThresholds, detect_region

GENERAL_LIMITATION = (
    "These are visual estimates that can be affected by lighting, camera "
    "quality, image resolution, makeup, filters, and shadows."
)
DRYNESS_LIMITATION = (
    "Apparent dryness is not reliably estimated from a standard photo and "
    "is not included in this analysis."
)
MULTIPLE_FACES_LIMITATION_TEMPLATE = (
    "{count} faces were detected in the image; only the largest was analyzed."
)
FALLBACK_REGION_LIMITATION = (
    "No face was reliably detected; a centered region of the image was "
    "analyzed instead, which may not correspond to skin."
)


class VisualAnalysisPipelineResult:
    """Plain container for the analyzer's output (not an API schema)."""

    def __init__(
        self,
        observations: list[VisualObservation],
        limitations: list[str],
        region: RegionResult,
    ) -> None:
        self.observations = observations
        self.limitations = limitations
        self.region = region


def run_visual_analysis(
    image: Image.Image, settings: Settings, quality_score: float
) -> VisualAnalysisPipelineResult:
    """Run the full Phase 3 pipeline on an already quality-accepted image.

    ``quality_score`` (the Phase 2 result for this same image) feeds the
    heuristic confidence calculation -- a lower-quality (but still
    accepted) image yields lower-confidence observations.
    """
    oriented, _orientation = preprocessing.normalize_orientation(image)
    resized = preprocessing.resize_for_analysis(oriented, settings.vision_max_analysis_dimension)
    bgr = preprocessing.to_bgr_array(resized)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    region_thresholds = RegionThresholds.from_settings(settings)
    region = detect_region(gray, region_thresholds)
    x1, y1, x2, y2 = region.box
    roi = bgr[y1:y2, x1:x2]

    confidence = compute_confidence(
        quality_score=quality_score,
        region_is_detected_face=(region.source == RegionSource.DETECTED_FACE),
    )

    redness_result = redness.analyze_redness(roi, redness.RednessThresholds.from_settings(settings))
    texture_result = texture.analyze_texture(roi, texture.TextureThresholds.from_settings(settings))
    shine_result = shine.analyze_shine(roi, shine.ShineThresholds.from_settings(settings))
    tone_result = tone.analyze_tone(roi, tone.ToneThresholds.from_settings(settings))
    spots_result = spots.analyze_spots(roi, spots.SpotsThresholds.from_settings(settings))

    observations = [
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level=redness_result.level,
            score=redness_result.score,
            confidence=confidence,
            method=redness_result.method,
            note=redness_result.note,
        ),
        VisualObservation(
            feature=ObservationFeature.VISIBLE_TEXTURE,
            level=texture_result.level,
            score=texture_result.score,
            confidence=confidence,
            method=texture_result.method,
            note=texture_result.note,
        ),
        VisualObservation(
            feature=ObservationFeature.SHINE_OILINESS,
            level=shine_result.level,
            score=shine_result.score,
            confidence=confidence,
            method=shine_result.method,
            note=shine_result.note,
        ),
        VisualObservation(
            feature=ObservationFeature.UNEVEN_TONE,
            level=tone_result.level,
            score=tone_result.score,
            confidence=confidence,
            method=tone_result.method,
            note=tone_result.note,
        ),
        VisualObservation(
            feature=ObservationFeature.VISIBLE_SPOTS_MARKS,
            level=spots_result.level,
            score=spots_result.score,
            confidence=confidence,
            method=spots_result.method,
            note=spots_result.note,
        ),
    ]

    limitations = [GENERAL_LIMITATION, DRYNESS_LIMITATION]
    if region.source == RegionSource.CENTER_CROP_FALLBACK:
        limitations.append(FALLBACK_REGION_LIMITATION)
    if region.faces_detected > 1:
        limitations.append(MULTIPLE_FACES_LIMITATION_TEMPLATE.format(count=region.faces_detected))

    return VisualAnalysisPipelineResult(
        observations=observations, limitations=limitations, region=region
    )
