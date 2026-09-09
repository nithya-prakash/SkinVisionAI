"""Image metadata and image-quality-check schemas.

The quality-check *implementation* (blur/brightness/resolution detection)
belongs to Phase 2. This module only defines the typed contract its result
must satisfy, so the Phase 2 pipeline and the API layer can be built against
a stable shape now.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_IMAGE_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)


class ImageQualityIssue(StrEnum):
    """Specific, non-diagnostic reasons an image may be unsuitable for analysis."""

    TOO_LOW_RESOLUTION = "too_low_resolution"
    TOO_BLURRY = "too_blurry"
    TOO_DARK = "too_dark"
    OVEREXPOSED = "overexposed"
    EXTREME_SHADOWS = "extreme_shadows"
    LOW_CONTRAST = "low_contrast"
    UNSUPPORTED_FORMAT = "unsupported_format"
    UNSUPPORTED_ORIENTATION = "unsupported_orientation"
    INSUFFICIENT_SKIN_VISIBILITY = "insufficient_skin_visibility"


class ImageQualityMetrics(BaseModel):
    """Raw technical measurements behind a quality result.

    Purely technical image-processing metrics -- never a skin or medical
    measurement. See ``app.vision.quality`` (Phase 2) for how these are
    computed and ``docs/vision.md`` for the methodology.
    """

    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: float = Field(gt=0)
    file_size_bytes: int = Field(gt=0)
    blur_score: float = Field(
        description="Variance of the Laplacian; higher means sharper."
    )
    brightness_score: float = Field(
        ge=0.0, le=255.0, description="Mean grayscale pixel intensity, 0-255."
    )
    contrast_score: float = Field(
        ge=0.0, description="Standard deviation of grayscale pixel intensity."
    )
    orientation: int | None = Field(
        default=None, description="EXIF orientation tag (1-8), if present."
    )


class ImageQualityResult(BaseModel):
    """Outcome of the pre-analysis image quality gate (Phase 2).

    ``is_acceptable`` gates whether visual analysis may proceed at all;
    ``score`` is a coarse 0-1 heuristic quality estimate, not a confidence
    in any medical sense.
    """

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    is_acceptable: bool
    issues: list[ImageQualityIssue] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Human-readable guidance, e.g. asking the user to retake the photo.",
    )
    metrics: ImageQualityMetrics | None = Field(
        default=None,
        description="Raw metrics behind this result. None until Phase 2's analyzer runs.",
    )


class ImageMetadataBase(BaseModel):
    """Fields common to image metadata creation and reads."""

    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(gt=0)
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)

    @field_validator("content_type")
    @classmethod
    def _validate_content_type(cls, value: str) -> str:
        if value not in SUPPORTED_IMAGE_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported image content type '{value}'. "
                f"Supported: {sorted(SUPPORTED_IMAGE_CONTENT_TYPES)}"
            )
        return value


class ImageMetadataCreate(ImageMetadataBase):
    """Payload accepted when registering a freshly uploaded image."""

    session_id: UUID


class ImageMetadataRead(ImageMetadataBase):
    """Image metadata as returned by the API. Never includes raw image bytes
    or a server filesystem path.
    """

    id: UUID
    session_id: UUID
    content_hash: str
    quality_result: ImageQualityResult | None = None
    created_at: datetime


class ImageUploadResponse(BaseModel):
    """Response for ``POST /api/analysis/upload`` (Phase 2).

    Upload succeeds (and this is returned) even when the quality gate
    rejects the image -- ``quality.is_acceptable`` communicates the gate
    outcome; the user is expected to retry with a new image rather than
    receiving an HTTP error for a merely low-quality (but valid) photo.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID
    session_id: UUID
    image: ImageMetadataRead
    quality: ImageQualityResult
