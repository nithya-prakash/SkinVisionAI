"""Image ingestion orchestration (Phase 2).

API route -> image_service -> upload_validation -> vision.quality ->
Pydantic result -> database persistence. Keeps the API route a thin HTTP
boundary and the validation/analysis logic independently testable.

Never logs image bytes, and only ever logs the sanitized filename (never
the client-supplied one verbatim).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.upload_validation import (
    load_and_validate_image,
    sanitize_filename,
    validate_content_type,
    validate_upload_size,
)
from app.models.analysis import SkinAnalysis
from app.models.image import ImageMetadata
from app.schemas.analysis import AnalysisStatus
from app.schemas.image import ImageMetadataRead, ImageUploadResponse
from app.services.session_service import get_or_create_session
from app.vision.quality import QualityThresholds, analyze_image_quality

logger = logging.getLogger(__name__)


def _persist_to_disk(raw_bytes: bytes, image_format: str, upload_directory: Path) -> str:
    """Write the image under a server-generated name. The client-supplied
    filename is never used to build this path.
    """
    upload_directory.mkdir(parents=True, exist_ok=True)
    extension = "jpg" if image_format == "JPEG" else "png"
    destination = upload_directory / f"{uuid.uuid4().hex}.{extension}"
    destination.write_bytes(raw_bytes)
    return str(destination)


async def ingest_image(
    *,
    db: AsyncSession,
    settings: Settings,
    session_id: str | None,
    upload: UploadFile,
) -> ImageUploadResponse:
    """Validate, quality-check, and persist one uploaded image.

    Raises ``app.core.upload_validation.UploadValidationError`` for hard
    validation failures (bad format, corrupted content, oversized file).
    A merely low-quality-but-valid image is not an error: it is persisted
    and returned with ``quality.is_acceptable=False`` so the caller can
    show the rejection reasons and let the user retry.
    """
    raw_bytes = await upload.read()
    validate_upload_size(len(raw_bytes), settings.image_max_size_mb)
    validate_content_type(upload.content_type)
    image = load_and_validate_image(raw_bytes)

    safe_filename = sanitize_filename(upload.filename)
    content_hash = hashlib.sha256(raw_bytes).hexdigest()

    thresholds = QualityThresholds.from_settings(settings)
    quality_result = analyze_image_quality(image, thresholds, file_size_bytes=len(raw_bytes))
    assert quality_result.metrics is not None  # always set by analyze_image_quality

    session = await get_or_create_session(db, session_id)

    storage_path: str | None = None
    if settings.image_retention_mode == "temporary":
        storage_path = _persist_to_disk(raw_bytes, image.format, settings.upload_directory)

    image_row = ImageMetadata(
        session_id=session.id,
        storage_path=storage_path,
        content_hash=content_hash,
        original_filename=safe_filename,
        content_type=f"image/{image.format.lower()}",
        width_px=quality_result.metrics.width,
        height_px=quality_result.metrics.height,
        size_bytes=len(raw_bytes),
        quality_result=quality_result.model_dump(mode="json"),
    )
    db.add(image_row)
    await db.flush()

    analysis_row = SkinAnalysis(
        session_id=session.id,
        image_id=image_row.id,
        status=AnalysisStatus.IMAGE_UPLOADED.value,
    )
    db.add(analysis_row)
    await db.commit()
    await db.refresh(image_row)
    await db.refresh(analysis_row)

    logger.info(
        "image_uploaded analysis_id=%s session_id=%s is_acceptable=%s issues=%s retained=%s",
        analysis_row.id,
        session.id,
        quality_result.is_acceptable,
        [issue.value for issue in quality_result.issues],
        storage_path is not None,
    )

    return ImageUploadResponse(
        analysis_id=analysis_row.id,
        session_id=session.id,
        image=ImageMetadataRead(
            id=image_row.id,
            session_id=session.id,
            original_filename=image_row.original_filename,
            content_type=image_row.content_type,
            size_bytes=image_row.size_bytes,
            width_px=image_row.width_px,
            height_px=image_row.height_px,
            content_hash=image_row.content_hash,
            quality_result=quality_result,
            created_at=image_row.created_at,
        ),
        quality=quality_result,
    )
