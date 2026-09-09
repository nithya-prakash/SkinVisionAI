"""Tests for app.vision.quality -- the non-diagnostic image quality gate.

All test images are synthetic (see tests/helpers/images.py). Assertions
check the deterministic quality-gate *behavior* (which issues fire, when
the gate accepts/rejects) rather than pinning exact heuristic score values,
so the tests stay meaningful if the scoring formula is tuned later.
"""
from __future__ import annotations

from PIL import Image

from app.schemas.image import ImageQualityIssue
from app.vision.quality import QualityThresholds, analyze_image_quality
from tests.helpers.images import (
    make_acceptable_image,
    make_bright_image,
    make_dark_image,
    make_low_contrast_image,
    make_sharp_image,
    make_tiny_image,
)

DEFAULT_THRESHOLDS = QualityThresholds(
    min_width_px=400,
    min_height_px=400,
    blur_variance_threshold=80.0,
    brightness_min=40.0,
    brightness_max=215.0,
    contrast_min_std=15.0,
)


def _blurred(image: Image.Image, radius: int = 14) -> Image.Image:
    from PIL import ImageFilter

    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def test_acceptable_image_passes_every_check() -> None:
    image = make_acceptable_image(800, 800)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=12345)

    assert result.is_acceptable is True
    assert result.issues == []
    assert result.message is None
    assert 0.0 <= result.score <= 1.0
    assert result.metrics is not None
    assert result.metrics.width == 800
    assert result.metrics.height == 800


def test_blurry_image_flagged_too_blurry() -> None:
    sharp = make_sharp_image(800, 800)
    blurry = _blurred(sharp)

    sharp_result = analyze_image_quality(sharp, DEFAULT_THRESHOLDS, file_size_bytes=1)
    blurry_result = analyze_image_quality(blurry, DEFAULT_THRESHOLDS, file_size_bytes=1)

    assert blurry_result.metrics.blur_score < sharp_result.metrics.blur_score
    assert ImageQualityIssue.TOO_BLURRY in blurry_result.issues
    assert blurry_result.is_acceptable is False


def test_dark_image_flagged_too_dark() -> None:
    image = make_dark_image(800, 800)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)

    assert ImageQualityIssue.TOO_DARK in result.issues
    assert result.is_acceptable is False
    assert result.metrics.brightness_score < DEFAULT_THRESHOLDS.brightness_min


def test_overexposed_image_flagged() -> None:
    image = make_bright_image(800, 800)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)

    assert ImageQualityIssue.OVEREXPOSED in result.issues
    assert result.is_acceptable is False
    assert result.metrics.brightness_score > DEFAULT_THRESHOLDS.brightness_max


def test_low_contrast_image_flagged() -> None:
    image = make_low_contrast_image(800, 800)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)

    assert ImageQualityIssue.LOW_CONTRAST in result.issues
    assert result.is_acceptable is False


def test_tiny_image_flagged_too_low_resolution() -> None:
    image = make_tiny_image(50, 50)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)

    assert ImageQualityIssue.TOO_LOW_RESOLUTION in result.issues
    assert result.is_acceptable is False
    assert result.message == "Image quality is insufficient for reliable visual analysis."


def test_rejected_image_never_contains_a_medical_or_diagnostic_message() -> None:
    """Guard against scope creep: quality messages must stay technical."""
    for factory in (make_dark_image, make_bright_image, make_tiny_image, make_low_contrast_image):
        result = analyze_image_quality(factory(), DEFAULT_THRESHOLDS, file_size_bytes=1)
        text = (result.message or "").lower()
        for banned in ("acne", "rosacea", "eczema", "melanoma", "diagnos", "condition"):
            assert banned not in text


# --- resolution boundary ---


def test_resolution_exactly_at_minimum_is_accepted() -> None:
    from tests.helpers.images import _noisy_array

    image = Image.fromarray(_noisy_array(400, 400, base=128, spread=90))
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)
    assert ImageQualityIssue.TOO_LOW_RESOLUTION not in result.issues


def test_resolution_one_pixel_below_minimum_is_rejected() -> None:
    from tests.helpers.images import _noisy_array

    image = Image.fromarray(_noisy_array(399, 400, base=128, spread=90))
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)
    assert ImageQualityIssue.TOO_LOW_RESOLUTION in result.issues


# --- metadata extraction ---


def test_metadata_extraction_reports_correct_dimensions_and_aspect_ratio() -> None:
    image = make_acceptable_image(640, 480)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=99999)

    assert result.metrics.width == 640
    assert result.metrics.height == 480
    assert result.metrics.aspect_ratio == round(640 / 480, 4)
    assert result.metrics.file_size_bytes == 99999


def test_metadata_extraction_reads_exif_orientation_when_present() -> None:
    image = make_acceptable_image(400, 400)
    exif = Image.Exif()
    exif[274] = 6  # rotated 90 CW
    import io

    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    reloaded = Image.open(buf)

    result = analyze_image_quality(reloaded, DEFAULT_THRESHOLDS, file_size_bytes=1)
    assert result.metrics.orientation == 6


def test_metadata_extraction_orientation_is_none_when_absent() -> None:
    image = make_acceptable_image(400, 400)
    result = analyze_image_quality(image, DEFAULT_THRESHOLDS, file_size_bytes=1)
    assert result.metrics.orientation is None
