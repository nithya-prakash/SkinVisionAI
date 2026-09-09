"""Region-of-interest (ROI) selection for the visual-observation pipeline.

Uses OpenCV's bundled Haar-cascade frontal-face detector -- a small,
classical (Viola-Jones) detector shipped inside opencv-python-headless
itself, requiring no download and no large pretrained model. This is a
*localization* step only: it finds a bounding box to analyze, and produces
no facial identity, embedding, or landmark data, and none is stored --
nothing here can or does identify a person.

The system must handle "no detectable face" gracefully rather than
hallucinate a result, so a face-less or detection-failed image always
falls back to a deterministic center crop.
"""
from __future__ import annotations

from functools import lru_cache

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.schemas.vision import RegionSource

# Bundled with opencv-python-headless; no network download required.
_FRONTAL_FACE_CASCADE = "haarcascade_frontalface_default.xml"

# Below this pixel size in either dimension, a cropped region can't yield a
# meaningful measurement -- fall back rather than analyze a sliver.
_MIN_REGION_DIMENSION_PX = 40


class RegionThresholds(BaseModel):
    """Configurable region-of-interest parameters. See docs/vision.md."""

    model_config = ConfigDict(extra="forbid")

    face_min_size_fraction: float
    face_margin_fraction: float
    center_crop_fraction: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RegionThresholds":
        return cls(
            face_min_size_fraction=settings.vision_face_min_size_fraction,
            face_margin_fraction=settings.vision_face_margin_fraction,
            center_crop_fraction=settings.vision_center_crop_fraction,
        )


class RegionResult(BaseModel):
    """The selected analysis region and how it was chosen."""

    model_config = ConfigDict(extra="forbid")

    source: RegionSource
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in the image's own pixel coordinates
    faces_detected: int


@lru_cache(maxsize=1)
def _load_face_cascade() -> cv2.CascadeClassifier:
    cascade_path = f"{cv2.data.haarcascades}{_FRONTAL_FACE_CASCADE}"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise RuntimeError(f"Failed to load bundled Haar cascade at {cascade_path}")
    return cascade


def _center_crop_box(width: int, height: int, crop_fraction: float) -> tuple[int, int, int, int]:
    side = max(_MIN_REGION_DIMENSION_PX, round(min(width, height) * crop_fraction))
    side = min(side, width, height)
    x1 = (width - side) // 2
    y1 = (height - side) // 2
    return (x1, y1, x1 + side, y1 + side)


def _expand_and_clip(
    x: int, y: int, w: int, h: int, margin_fraction: float, width: int, height: int
) -> tuple[int, int, int, int]:
    margin_x = round(w * margin_fraction)
    margin_y = round(h * margin_fraction)
    x1 = max(0, x - margin_x)
    y1 = max(0, y - margin_y)
    x2 = min(width, x + w + margin_x)
    y2 = min(height, y + h + margin_y)
    return (x1, y1, x2, y2)


def detect_region(gray: np.ndarray, thresholds: RegionThresholds) -> RegionResult:
    """Select the region of the (grayscale) image to run feature extraction
    on: the largest sufficiently-large detected face (expanded by a margin
    to include surrounding skin), or a deterministic center crop if no face
    is detected or reliable detection isn't possible.
    """
    height, width = gray.shape[:2]
    min_face_px = round(min(width, height) * thresholds.face_min_size_fraction)

    cascade = _load_face_cascade()
    detections = cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(min_face_px, min_face_px),
    )

    if len(detections) == 0:
        box = _center_crop_box(width, height, thresholds.center_crop_fraction)
        return RegionResult(source=RegionSource.CENTER_CROP_FALLBACK, box=box, faces_detected=0)

    # Multiple faces: analyze only the largest (most likely the intended
    # subject), and report how many were seen so the caller can surface a
    # limitation about the others being ignored.
    fx, fy, fw, fh = max(detections, key=lambda d: d[2] * d[3])
    box = _expand_and_clip(fx, fy, fw, fh, thresholds.face_margin_fraction, width, height)

    if (box[2] - box[0]) < _MIN_REGION_DIMENSION_PX or (box[3] - box[1]) < _MIN_REGION_DIMENSION_PX:
        fallback_box = _center_crop_box(width, height, thresholds.center_crop_fraction)
        return RegionResult(
            source=RegionSource.CENTER_CROP_FALLBACK,
            box=fallback_box,
            faces_detected=len(detections),
        )

    return RegionResult(
        source=RegionSource.DETECTED_FACE, box=box, faces_detected=len(detections)
    )
