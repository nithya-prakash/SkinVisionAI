"""Visual-analysis orchestration (Phase 3).

API route -> vision_service -> (reused Phase 2 validation/quality data) ->
app.vision.analyzer -> Pydantic result -> DB persistence. Mirrors the
Phase 2 image_service's layering.

Reuses Phase 2's persisted quality gate result rather than re-running or
duplicating quality analysis: an image that failed (or was never run
through) the Phase 2 gate is refused here, not silently re-graded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.analysis import SkinAnalysis
from app.models.image import ImageMetadata
from app.schemas.analysis import AnalysisStatus
from app.schemas.vision import VisualAnalysisResult
from app.vision.analyzer import run_visual_analysis

logger = logging.getLogger(__name__)


class VisualAnalysisError(Exception):
    """A user-correctable or environment problem, mapped to an HTTP status
    by the API route.
    """

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def analyze_visual_features(
    *, db: AsyncSession, settings: Settings, analysis_id: UUID
) -> VisualAnalysisResult:
    analysis = await db.get(SkinAnalysis, analysis_id)
    if analysis is None:
        raise VisualAnalysisError(
            code="analysis_not_found",
            message="No analysis exists with that id.",
            status_code=404,
        )

    image = await db.get(ImageMetadata, analysis.image_id)
    if image is None:
        raise VisualAnalysisError(
            code="image_not_found",
            message="The image associated with this analysis no longer exists.",
            status_code=404,
        )

    quality_result = image.quality_result or {}
    if not quality_result.get("is_acceptable"):
        issues = quality_result.get("issues", [])
        raise VisualAnalysisError(
            code="quality_gate_not_passed",
            message=(
                "This image did not pass the Phase 2 quality gate and cannot be "
                f"analyzed. Issues: {', '.join(issues) if issues else 'unknown'}. "
                "Upload a new photo."
            ),
            status_code=422,
        )

    if not image.storage_path:
        raise VisualAnalysisError(
            code="image_not_retained",
            message=(
                "This image was processed with retention disabled and is no "
                "longer available for further analysis. Re-upload with "
                "retention enabled to run visual analysis."
            ),
            status_code=409,
        )

    # Phase 8: mark the row "analyzing" before any file I/O or pipeline
    # work, and "failed" on any error from here on, so a crash never
    # leaves it silently stuck at its prior status forever -- see
    # docs/persistence.md's analysis lifecycle. Committed separately from
    # the final result so the in-progress state is visible even if the
    # pipeline itself hangs or crashes hard (the synchronous pipeline
    # today makes this window short, but the behavior is correct
    # regardless).
    analysis.status = AnalysisStatus.ANALYZING.value
    await db.commit()

    try:
        raw_bytes = Path(image.storage_path).read_bytes()
    except FileNotFoundError:
        analysis.status = AnalysisStatus.FAILED.value
        await db.commit()
        raise VisualAnalysisError(
            code="image_file_missing",
            message="The stored image file is unavailable.",
            status_code=404,
        ) from None

    try:
        with Image.open(BytesIO(raw_bytes)) as pil_image:
            pil_image.load()
            quality_score = float(quality_result.get("score", 0.0))
            pipeline_result = run_visual_analysis(pil_image, settings, quality_score)
    except (UnidentifiedImageError, OSError, ValueError):
        analysis.status = AnalysisStatus.FAILED.value
        await db.commit()
        raise VisualAnalysisError(
            code="image_file_missing",
            message="The stored image file could not be read.",
            status_code=404,
        ) from None
    except Exception:
        analysis.status = AnalysisStatus.FAILED.value
        await db.commit()
        logger.exception("visual_analysis_failed analysis_id=%s", analysis.id)
        raise

    result = VisualAnalysisResult(
        analysis_id=analysis.id,
        image_id=image.id,
        observations=pipeline_result.observations,
        region_used=pipeline_result.region.source,
        limitations=pipeline_result.limitations,
        created_at=datetime.now(timezone.utc),
    )

    analysis.visual_observations = [obs.model_dump(mode="json") for obs in result.observations]
    analysis.structured_response = result.model_dump(mode="json")
    analysis.status = AnalysisStatus.COMPLETED.value
    await db.commit()

    logger.info(
        "visual_analysis_completed analysis_id=%s region=%s faces_detected=%s observation_count=%s",
        analysis.id,
        pipeline_result.region.source.value,
        pipeline_result.region.faces_detected,
        len(result.observations),
    )

    return result
