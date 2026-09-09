"""Deterministic image preprocessing shared by the quality gate (Phase 2)
and the visual-observation pipeline (Phase 3).

Every step here is deterministic (no randomness) so the same input image
and configuration always produce the same output -- required for the
pipeline's reproducibility guarantee. Preprocessing never destroys the
original uploaded file; it only ever operates on an in-memory copy.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageOps

_EXIF_ORIENTATION_TAG = 274


def read_exif_orientation(image: Image.Image) -> int | None:
    """Return the raw EXIF orientation tag (1-8) if present, else None."""
    try:
        value = image.getexif().get(_EXIF_ORIENTATION_TAG)
    except Exception:
        return None
    return int(value) if value is not None else None


def normalize_orientation(image: Image.Image) -> tuple[Image.Image, int | None]:
    """Return an EXIF-orientation-corrected copy of ``image``, plus the
    original orientation tag (for reporting) if one was present.

    Used by both the Phase 2 quality gate and the Phase 3 feature
    extractors so metrics and observations describe the image the way a
    viewer would actually see it -- not its raw, possibly-rotated encoding.
    """
    orientation = read_exif_orientation(image)
    oriented = ImageOps.exif_transpose(image) or image
    return oriented, orientation


def resize_for_analysis(image: Image.Image, max_dimension: int) -> Image.Image:
    """Downscale ``image`` so its longest edge is at most ``max_dimension``.

    A pure performance/determinism knob for Phase 3's feature extraction --
    it does not affect the Phase 2 quality gate, which measures the
    full-resolution image. Images already at or below the limit are
    returned unchanged. Never upscales.
    """
    width, height = image.size
    longest_edge = max(width, height)
    if longest_edge <= max_dimension:
        return image

    scale = max_dimension / longest_edge
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def to_bgr_array(image: Image.Image) -> np.ndarray:
    """Convert a PIL image to an OpenCV-style BGR NumPy array."""
    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
