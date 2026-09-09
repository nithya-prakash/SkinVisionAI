"""Tests for app.core.upload_validation."""
from __future__ import annotations

import pytest

from app.core.upload_validation import (
    UploadValidationError,
    load_and_validate_image,
    sanitize_filename,
    validate_content_type,
    validate_upload_size,
)
from tests.helpers.images import (
    corrupted_jpeg_bytes,
    decompression_bomb_png_bytes,
    make_acceptable_image,
    not_an_image_bytes,
    to_bytes,
)


# --- sanitize_filename: path traversal / malformed filename handling ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("selfie.jpg", "selfie.jpg"),
        ("../../etc/passwd.jpg", "passwd.jpg"),
        ("..\\..\\windows\\system32\\evil.jpg", "evil.jpg"),
        ("/etc/passwd", "passwd"),
        ("a" * 300 + ".jpg", ("a" * 300 + ".jpg")[:255]),
        ("weird name with spaces!.jpg", "weird_name_with_spaces_.jpg"),
        ("", "upload"),
        (None, "upload"),
        ("....", "upload"),
        ("file\x00.jpg.exe", "file"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_never_contains_path_separators() -> None:
    result = sanitize_filename("../../../malicious/../path/x.jpg")
    assert "/" not in result
    assert "\\" not in result
    assert ".." not in result


@pytest.mark.parametrize(
    "malicious_filename",
    [
        "../../secret.jpg",
        "../../../etc/passwd",
        "foo;rm -rf.jpg",
        "<script>.jpg",
    ],
)
def test_sanitize_filename_neutralizes_brief_example_attacks(malicious_filename: str) -> None:
    """The exact four example filenames from the Phase 10 brief. The
    result is display-only metadata -- it never participates in building
    a filesystem path (the real on-disk name is always a fresh UUID, see
    app.services.image_service) -- but it must still come back free of
    path separators, ``..``, and shell/HTML metacharacters, since it is
    echoed back to the client as ``ImageMetadataRead.original_filename``.
    """
    result = sanitize_filename(malicious_filename)
    assert "/" not in result
    assert "\\" not in result
    assert ".." not in result
    assert ";" not in result
    assert "<" not in result
    assert ">" not in result
    assert " " not in result


# --- validate_upload_size ---


def test_validate_upload_size_accepts_within_limit() -> None:
    validate_upload_size(1024, max_size_mb=8)


def test_validate_upload_size_rejects_empty() -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload_size(0, max_size_mb=8)
    assert exc_info.value.code == "empty_file"


def test_validate_upload_size_rejects_oversized() -> None:
    too_big = 9 * 1024 * 1024
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload_size(too_big, max_size_mb=8)
    assert exc_info.value.code == "file_too_large"
    assert exc_info.value.status_code == 413


def test_validate_upload_size_boundary_exact_limit_is_accepted() -> None:
    exactly_max = 8 * 1024 * 1024
    validate_upload_size(exactly_max, max_size_mb=8)


def test_validate_upload_size_boundary_one_byte_over_is_rejected() -> None:
    one_over = 8 * 1024 * 1024 + 1
    with pytest.raises(UploadValidationError):
        validate_upload_size(one_over, max_size_mb=8)


# --- validate_content_type ---


@pytest.mark.parametrize("content_type", ["image/jpeg", "image/png"])
def test_validate_content_type_accepts_supported(content_type: str) -> None:
    validate_content_type(content_type)


@pytest.mark.parametrize(
    "content_type", ["image/gif", "image/bmp", "image/webp", "text/plain", "", None]
)
def test_validate_content_type_rejects_unsupported(content_type: str | None) -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        validate_content_type(content_type)
    assert exc_info.value.status_code == 415
    assert exc_info.value.code == "unsupported_format"


# --- load_and_validate_image ---


def test_load_and_validate_image_accepts_valid_jpeg() -> None:
    raw = to_bytes(make_acceptable_image(400, 400), "JPEG")
    image = load_and_validate_image(raw)
    assert image.format == "JPEG"


def test_load_and_validate_image_accepts_valid_png() -> None:
    raw = to_bytes(make_acceptable_image(400, 400), "PNG")
    image = load_and_validate_image(raw)
    assert image.format == "PNG"


def test_load_and_validate_image_rejects_fake_image_with_image_mimetype() -> None:
    """Bytes that are not an image at all, regardless of any claimed Content-Type."""
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(not_an_image_bytes())
    assert exc_info.value.code == "invalid_image_content"
    assert exc_info.value.status_code == 400


def test_load_and_validate_image_rejects_corrupted_image() -> None:
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(corrupted_jpeg_bytes())
    assert exc_info.value.code == "invalid_image_content"


def test_load_and_validate_image_rejects_unsupported_real_format() -> None:
    """A real, valid image, but in a format outside {JPEG, PNG} (here: BMP)."""
    raw = to_bytes(make_acceptable_image(400, 400), "BMP")
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(raw)
    assert exc_info.value.code == "unsupported_format"
    assert exc_info.value.status_code == 415


# --- Decompression-bomb protection (Phase 10) ---


def test_load_and_validate_image_rejects_oversized_decoded_dimensions() -> None:
    """A small file (a few dozen bytes) whose header declares an enormous
    decoded pixel count -- must be rejected as a controlled 400 before
    any expensive per-pixel work, never an unhandled 500.
    """
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(decompression_bomb_png_bytes())
    assert exc_info.value.code == "image_too_large_decoded"
    assert exc_info.value.status_code == 400


def test_load_and_validate_image_rejects_dimensions_just_over_the_warning_threshold() -> None:
    """Pillow only *warns* (DecompressionBombWarning), rather than raising
    outright, for a decoded size that exceeds MAX_IMAGE_PIXELS but not by
    the larger margin DecompressionBombError requires -- this must still
    be rejected, not silently allowed through as "just a warning".
    """
    from PIL import Image as PILImage

    # Roughly 1.5x the default MAX_IMAGE_PIXELS threshold: past the
    # warning line, comfortably short of the hard-error line.
    side = int((PILImage.MAX_IMAGE_PIXELS * 1.5) ** 0.5)
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(decompression_bomb_png_bytes(side, side))
    assert exc_info.value.code == "image_too_large_decoded"


def test_load_and_validate_image_still_accepts_a_normal_large_photo() -> None:
    """The decompression-bomb guard must not over-trigger on an ordinary,
    legitimately large (but nowhere near the pixel-count threshold) photo.
    """
    raw = to_bytes(make_acceptable_image(3000, 2000), "JPEG")
    image = load_and_validate_image(raw)
    assert image.size == (3000, 2000)


def test_load_and_validate_image_rejects_malformed_content_not_decompression_bomb() -> None:
    """Distinguishes the two failure codes: a corrupted/non-image file
    must still get 'invalid_image_content', not be miscategorized as a
    decompression bomb just because both are caught in the same function.
    """
    with pytest.raises(UploadValidationError) as exc_info:
        load_and_validate_image(corrupted_jpeg_bytes())
    assert exc_info.value.code == "invalid_image_content"
