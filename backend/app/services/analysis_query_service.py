"""Analysis retrieval (Phase 8).

Read-only counterpart to Phase 2/3's ``image_service``/``vision_service``:
those write ``SkinAnalysis``/``ImageMetadata`` rows, this reads them back
without recomputing anything. ``GET /api/analysis/{id}`` never re-runs
the quality gate or the vision pipeline -- it reports exactly what was
already persisted, or an explicit "not yet analyzed" state, never a
fabricated result.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import SkinAnalysis
from app.models.image import ImageMetadata
from app.schemas.analysis import AnalysisClientStatus, AnalysisDetailResponse, AnalysisStatus
from app.schemas.image import ImageMetadataRead, ImageQualityResult
from app.schemas.vision import VisualAnalysisResult


class AnalysisNotFoundError(Exception):
    """Raised when a requested ``analysis_id`` does not exist."""


def derive_client_status(analysis: SkinAnalysis, image: ImageMetadata) -> AnalysisClientStatus:
    """Map the stored ``AnalysisStatus`` (plus the image's already-computed
    quality result) to the client-facing status -- see
    ``AnalysisClientStatus``'s docstring for why this is derived rather
    than a sixth stored value.
    """
    if analysis.status == AnalysisStatus.COMPLETED.value:
        return AnalysisClientStatus.COMPLETED
    if analysis.status == AnalysisStatus.FAILED.value:
        return AnalysisClientStatus.FAILED
    if analysis.status == AnalysisStatus.ANALYZING.value:
        return AnalysisClientStatus.ANALYZING

    # PENDING or IMAGE_UPLOADED: split on the already-computed quality result.
    quality = image.quality_result or {}
    if quality.get("is_acceptable"):
        return AnalysisClientStatus.READY_FOR_VISUAL_ANALYSIS
    return AnalysisClientStatus.QUALITY_REJECTED


async def get_analysis_detail(db: AsyncSession, analysis_id) -> AnalysisDetailResponse:
    """Fetch one analysis by id. Raises ``AnalysisNotFoundError`` for an
    unknown id or an analysis whose image row is missing (should not
    happen given the ``ON DELETE CASCADE`` from ``ImageMetadata`` to
    ``SkinAnalysis``, but checked defensively rather than assumed).
    """
    analysis = await db.get(SkinAnalysis, analysis_id)
    if analysis is None:
        raise AnalysisNotFoundError(f"No analysis exists with id {analysis_id}")

    image = await db.get(ImageMetadata, analysis.image_id)
    if image is None:
        raise AnalysisNotFoundError(f"The image for analysis {analysis_id} no longer exists")

    client_status = derive_client_status(analysis, image)

    image_read = ImageMetadataRead(
        id=image.id,
        session_id=image.session_id,
        original_filename=image.original_filename,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        width_px=image.width_px,
        height_px=image.height_px,
        content_hash=image.content_hash,
        quality_result=ImageQualityResult.model_validate(image.quality_result)
        if image.quality_result
        else None,
        created_at=image.created_at,
    )

    visual_analysis = (
        VisualAnalysisResult.model_validate(analysis.structured_response)
        if client_status == AnalysisClientStatus.COMPLETED and analysis.structured_response
        else None
    )

    return AnalysisDetailResponse(
        id=analysis.id,
        session_id=analysis.session_id,
        status=client_status,
        image=image_read,
        visual_analysis=visual_analysis,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
    )
