"""Tests for app.schemas.image."""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.image import (
    ImageMetadataCreate,
    ImageMetadataRead,
    ImageQualityIssue,
    ImageQualityResult,
)


def test_image_quality_result_minimal_valid() -> None:
    result = ImageQualityResult(score=0.91, is_acceptable=True)
    assert result.issues == []
    assert result.message is None


def test_image_quality_result_with_issues() -> None:
    result = ImageQualityResult(
        score=0.2,
        is_acceptable=False,
        issues=[ImageQualityIssue.TOO_BLURRY, ImageQualityIssue.TOO_DARK],
        message="Image quality is insufficient for reliable visual analysis.",
    )
    assert result.is_acceptable is False
    assert ImageQualityIssue.TOO_BLURRY in result.issues


@pytest.mark.parametrize("bad_score", [-0.1, 1.1, 2.0])
def test_image_quality_result_rejects_out_of_range_score(bad_score: float) -> None:
    with pytest.raises(ValidationError):
        ImageQualityResult(score=bad_score, is_acceptable=True)


def test_image_quality_result_rejects_unknown_issue_string() -> None:
    with pytest.raises(ValidationError):
        ImageQualityResult(score=0.5, is_acceptable=False, issues=["not_a_real_issue"])


def test_image_quality_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ImageQualityResult(score=0.9, is_acceptable=True, diagnosis="acne")


def test_image_metadata_create_valid() -> None:
    payload = ImageMetadataCreate(
        session_id=uuid4(),
        original_filename="selfie.jpg",
        content_type="image/jpeg",
        size_bytes=204800,
        width_px=1024,
        height_px=768,
    )
    assert payload.content_type == "image/jpeg"


def test_image_metadata_create_optional_dimensions_may_be_omitted() -> None:
    payload = ImageMetadataCreate(
        session_id=uuid4(),
        original_filename="selfie.jpg",
        content_type="image/png",
        size_bytes=1024,
    )
    assert payload.width_px is None
    assert payload.height_px is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_filename", ""),
        ("size_bytes", 0),
        ("size_bytes", -5),
    ],
)
def test_image_metadata_create_rejects_invalid_values(field: str, value: object) -> None:
    base = dict(
        session_id=uuid4(),
        original_filename="selfie.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
    )
    base[field] = value
    with pytest.raises(ValidationError):
        ImageMetadataCreate(**base)


def test_image_metadata_create_rejects_unsupported_content_type() -> None:
    with pytest.raises(ValidationError):
        ImageMetadataCreate(
            session_id=uuid4(),
            original_filename="selfie.gif",
            content_type="image/gif",
            size_bytes=1024,
        )


def test_image_metadata_create_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        ImageMetadataCreate(original_filename="selfie.jpg", content_type="image/jpeg", size_bytes=1024)


def test_image_metadata_read_round_trip() -> None:
    read = ImageMetadataRead(
        id=uuid4(),
        session_id=uuid4(),
        original_filename="selfie.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        content_hash="a" * 64,
        quality_result=ImageQualityResult(score=0.9, is_acceptable=True),
        created_at="2026-01-01T00:00:00Z",
    )
    assert read.quality_result is not None
    assert read.quality_result.is_acceptable is True
