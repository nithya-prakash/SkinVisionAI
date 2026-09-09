"""Analysis endpoints.

Phase 2: image ingestion + quality gate (``POST /api/analysis/upload``).
Phase 3: visual-observation pipeline
(``POST /api/analysis/{analysis_id}/visual-analysis``). Phase 8:
retrieval (``GET /api/analysis/{analysis_id}``) -- reads back what was
already persisted, never recomputes.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.rate_limit import rate_limit_upload
from app.core.upload_validation import UploadValidationError
from app.database import get_db
from app.schemas.analysis import AnalysisDetailResponse
from app.schemas.image import ImageUploadResponse
from app.schemas.vision import VisualAnalysisResult
from app.services.analysis_query_service import AnalysisNotFoundError, get_analysis_detail
from app.services.image_service import ingest_image
from app.services.vision_service import VisualAnalysisError, analyze_visual_features

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post(
    "/upload",
    response_model=ImageUploadResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_upload)],
)
async def upload_image(
    file: UploadFile = File(..., description="JPEG or PNG image."),
    session_id: str | None = Form(
        default=None, description="Existing anonymous session id, if known."
    ),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImageUploadResponse:
    """Upload an image and run the non-diagnostic quality gate.

    Returns 201 with a structured result whether or not the quality gate
    accepts the image -- ``quality.is_acceptable`` communicates that, so
    the caller can show rejection reasons and let the user retry. Returns
    an HTTP error only for a hard validation failure: unsupported format
    (415), invalid/corrupted image content (400), or oversized upload (413).
    """
    try:
        return await ingest_image(
            db=db, settings=settings, session_id=session_id, upload=file
        )
    except UploadValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post(
    "/{analysis_id}/visual-analysis",
    response_model=VisualAnalysisResult,
    status_code=200,
)
async def run_visual_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VisualAnalysisResult:
    """Run the non-diagnostic visual-observation pipeline on a previously
    uploaded, quality-accepted image.

    Requires that ``analysis_id`` exists and its image both passed the
    Phase 2 quality gate and is still retained on disk. Returns a
    structured error (never a fabricated result) otherwise: 404 unknown
    analysis/missing image file, 422 quality gate not passed, 409 image
    not retained.
    """
    try:
        return await analyze_visual_features(db=db, settings=settings, analysis_id=analysis_id)
    except VisualAnalysisError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/{analysis_id}", response_model=AnalysisDetailResponse, status_code=200)
async def get_analysis(
    analysis_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalysisDetailResponse:
    """Retrieve a previously created analysis -- never recomputes the
    quality gate or the vision pipeline. ``status`` explicitly represents
    every stage (quality rejected, ready for visual analysis, analyzing,
    completed, failed) rather than a client having to infer it;
    ``visual_analysis`` is ``None`` until ``status`` is ``"completed"``.
    Never exposes a server filesystem path. 404 for an unknown id.
    """
    try:
        return await get_analysis_detail(db, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "analysis_not_found", "message": str(exc)},
        ) from exc
