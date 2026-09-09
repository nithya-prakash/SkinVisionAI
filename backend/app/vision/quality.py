"""Deterministic, non-diagnostic image quality analysis (Phase 2).

Computes technical image-quality metrics -- resolution, blur, brightness,
contrast -- with OpenCV/Pillow, and gates whether an image is suitable for
the Phase 3 visual-observation pipeline. This module never produces a skin
or medical assessment, only a technical readability judgment. See
``docs/vision.md`` for the methodology and threshold rationale.

Thresholds are centralized in ``QualityThresholds`` (sourced from
``app.config.Settings``) rather than scattered as magic numbers through the
analysis logic below.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.schemas.image import ImageQualityIssue, ImageQualityMetrics, ImageQualityResult
from app.vision._numeric import clip01
from app.vision.preprocessing import normalize_orientation

# How many brightness units outside [min, max] correspond to a fully-zeroed
# brightness component of the quality score (a scoring smoothness constant,
# not a pass/fail threshold -- those come from QualityThresholds).
_BRIGHTNESS_SCORE_FALLOFF = 60.0


class QualityThresholds(BaseModel):
    """Configurable quality-gate thresholds. See docs/vision.md for rationale."""

    model_config = ConfigDict(extra="forbid")

    min_width_px: int
    min_height_px: int
    blur_variance_threshold: float
    brightness_min: float
    brightness_max: float
    contrast_min_std: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "QualityThresholds":
        return cls(
            min_width_px=settings.image_min_width_px,
            min_height_px=settings.image_min_height_px,
            blur_variance_threshold=settings.image_blur_variance_threshold,
            brightness_min=settings.image_brightness_min,
            brightness_max=settings.image_brightness_max,
            contrast_min_std=settings.image_contrast_min_std,
        )


def _blur_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian -- a standard, well-understood focus measure.
    Low variance means few sharp edges, i.e. a blurry image.
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _brightness_score(gray: np.ndarray) -> float:
    """Mean grayscale pixel intensity, 0-255."""
    return float(gray.mean())


def _contrast_score(gray: np.ndarray) -> float:
    """Standard deviation of grayscale pixel intensity."""
    return float(gray.std())


def analyze_image_quality(
    image: Image.Image, thresholds: QualityThresholds, file_size_bytes: int
) -> ImageQualityResult:
    """Run the deterministic quality gate against a decoded image.

    Returns a structured, non-diagnostic result: a 0-1 heuristic quality
    score, an accept/reject gate, human-readable issue codes, and the raw
    metrics behind them. Never inspects skin content -- only generic
    image-processing signal.
    """
    # Normalize orientation before measuring, so metrics describe the
    # image as a viewer would actually see it.
    oriented, orientation = normalize_orientation(image)
    width, height = oriented.size
    gray = np.array(oriented.convert("L"))

    blur = _blur_score(gray)
    brightness = _brightness_score(gray)
    contrast = _contrast_score(gray)

    issues: list[ImageQualityIssue] = []
    if width < thresholds.min_width_px or height < thresholds.min_height_px:
        issues.append(ImageQualityIssue.TOO_LOW_RESOLUTION)
    if blur < thresholds.blur_variance_threshold:
        issues.append(ImageQualityIssue.TOO_BLURRY)
    if brightness < thresholds.brightness_min:
        issues.append(ImageQualityIssue.TOO_DARK)
    if brightness > thresholds.brightness_max:
        issues.append(ImageQualityIssue.OVEREXPOSED)
    if contrast < thresholds.contrast_min_std:
        issues.append(ImageQualityIssue.LOW_CONTRAST)

    resolution_component = clip01(
        min(width / thresholds.min_width_px, height / thresholds.min_height_px)
    )
    blur_component = clip01(blur / thresholds.blur_variance_threshold)
    if thresholds.brightness_min <= brightness <= thresholds.brightness_max:
        brightness_component = 1.0
    else:
        distance = min(
            abs(brightness - thresholds.brightness_min),
            abs(brightness - thresholds.brightness_max),
        )
        brightness_component = clip01(1.0 - distance / _BRIGHTNESS_SCORE_FALLOFF)
    contrast_component = clip01(contrast / thresholds.contrast_min_std)

    score = round(
        (resolution_component + blur_component + brightness_component + contrast_component)
        / 4,
        4,
    )
    is_acceptable = len(issues) == 0

    message = (
        None
        if is_acceptable
        else "Image quality is insufficient for reliable visual analysis."
    )

    metrics = ImageQualityMetrics(
        width=width,
        height=height,
        aspect_ratio=round(width / height, 4),
        file_size_bytes=file_size_bytes,
        blur_score=round(blur, 4),
        brightness_score=round(brightness, 4),
        contrast_score=round(contrast, 4),
        orientation=orientation,
    )

    return ImageQualityResult(
        score=score,
        is_acceptable=is_acceptable,
        issues=issues,
        message=message,
        metrics=metrics,
    )
