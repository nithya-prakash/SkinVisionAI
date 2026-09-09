"""Visible spots/marks estimation.

Method: a high-pass filter (absolute difference between a lightly
denoised copy of the grayscale region of interest and a heavily
Gaussian-blurred copy of itself) isolates small localized deviations from
the local average brightness. The resulting map is thresholded and
connected-component analysis counts compact blobs within a plausible size
range -- large enough to not be sensor noise, small enough to not be a
shadow or lighting gradient.

The median pre-blur exists specifically to keep ordinary photographic
sensor/JPEG noise from registering as thousands of one-pixel "spots" --
without it, this measurement was found (via testing against synthetic
noisy images) to spuriously count noise grain as marks by the thousands.
This is the one place denoising is used in the pipeline, and only because
this specific measurement (counting compact high-contrast blobs) is
otherwise dominated by pixel-level noise; it is not applied to the shared
preprocessed image other features use, since it would bias those.

This only counts and locates visually distinct localized marks. It never
classifies what a mark is -- not a mole, lesion, or any condition -- and
must always be described as "visible spots/marks."
"""
from __future__ import annotations

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.vision._numeric import clip01, score_to_level
from app.vision.features import FeatureScore

METHOD = "highpass_blob_count"

# Gaussian blur kernel used to build the local-average "baseline" that
# candidate spots are compared against. Large enough to represent overall
# regional shading rather than fine texture.
_BASELINE_BLUR_KERNEL = (31, 31)

# Median-filter kernel applied before high-pass filtering, to suppress
# single/few-pixel sensor and JPEG noise without erasing genuinely
# localized marks (which are larger than this kernel).
_DENOISE_KERNEL = 5


class SpotsThresholds(BaseModel):
    """Configurable visible-spots/marks thresholds. See docs/vision.md."""

    model_config = ConfigDict(extra="forbid")

    diff_threshold: int
    min_area_px: int
    max_area_fraction: float
    norm_max_count: int
    mild_min: float
    moderate_min: float
    pronounced_min: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "SpotsThresholds":
        return cls(
            diff_threshold=settings.vision_spots_diff_threshold,
            min_area_px=settings.vision_spots_min_area_px,
            max_area_fraction=settings.vision_spots_max_area_fraction,
            norm_max_count=settings.vision_spots_norm_max_count,
            mild_min=settings.vision_spots_mild_min,
            moderate_min=settings.vision_spots_moderate_min,
            pronounced_min=settings.vision_spots_pronounced_min,
        )


def analyze_spots(roi_bgr: np.ndarray, thresholds: SpotsThresholds) -> FeatureScore:
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.medianBlur(gray, _DENOISE_KERNEL)
    baseline = cv2.GaussianBlur(denoised, _BASELINE_BLUR_KERNEL, 0)
    diff = cv2.absdiff(denoised, baseline)

    _, mask = cv2.threshold(diff, thresholds.diff_threshold, 255, cv2.THRESH_BINARY)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    roi_area = gray.shape[0] * gray.shape[1]
    max_area_px = roi_area * thresholds.max_area_fraction

    spot_count = 0
    for label in range(1, num_labels):  # label 0 is the background
        area = stats[label, cv2.CC_STAT_AREA]
        if thresholds.min_area_px <= area <= max_area_px:
            spot_count += 1

    score = clip01(spot_count / thresholds.norm_max_count)
    level = score_to_level(
        score, thresholds.mild_min, thresholds.moderate_min, thresholds.pronounced_min
    )

    return FeatureScore(
        score=round(score, 4),
        level=level,
        method=METHOD,
        note=(
            f"Detected {spot_count} localized visual marks by size-filtered blob "
            "detection; does not identify what any mark is."
        ),
    )
