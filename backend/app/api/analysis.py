"""Analysis endpoints.

Phase 2: image ingestion + quality gate (``POST /api/analysis/upload``).
Phase 3: visual-observation pipeline
(``POST /api/analysis/{analysis_id}/visual-analysis``). Phase 8:
retrieval (``GET /api/analysis/{analysis_id}``) -- reads back what was
already persisted, never recomputes. Release-hardening follow-up: every
route requires authentication, and a ``{analysis_id}`` that exists but
belongs to a different user's session is a 403, not a 404 (a 404 here
would incorrectly imply the id itself is unknown) and never a
recomputed/fabricated result.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.rate_limit import rate_limit_upload
from app.core.upload_validation import UploadValidationError
from app.database import get_db
from app.models.analysis import SkinAnalysis
from app.models.user import User
from app.schemas.analysis import AnalysisDetailResponse
from app.schemas.image import ImageUploadResponse
from app.schemas.vision import VisualAnalysisResult
from app.services.analysis_query_service import AnalysisNotFoundError, get_analysis_detail
from app.services.auth_service import get_current_user
from app.services.image_service import ingest_image
from app.services.session_service import (
    SessionOwnershipError,
    assert_session_owned,
    get_or_create_session_for_user,
)
from app.services.vision_service import VisualAnalysisError, analyze_visual_features

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _ownership_forbidden(analysis_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": "analysis_forbidden",
            "message": f"Analysis {analysis_id} does not belong to the authenticated user.",
        },
    )


async def _assert_owns_analysis(db: AsyncSession, analysis_id: UUID, current_user: User) -> None:
    """404 for an unknown id, 403 for one that exists but isn't the
    caller's -- checked before any expensive work (the vision pipeline)
    runs, not just before the result is returned.
    """
    analysis = await db.get(SkinAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "analysis_not_found", "message": f"No analysis exists with id {analysis_id}"},
        )
    try:
        await assert_session_owned(db, analysis.session_id, current_user)
    except SessionOwnershipError as exc:
        raise _ownership_forbidden(analysis_id) from exc


@router.post(
    "/upload",
    response_model=ImageUploadResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_upload)],
)
async def upload_image(
    file: UploadFile = File(..., description="JPEG or PNG image."),
    session_id: str | None = Form(
        default=None, description="Caller's own session id, if known -- must belong to them."
    ),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    """Upload an image and run the non-diagnostic quality gate.

    Returns 201 with a structured result whether or not the quality gate
    accepts the image -- ``quality.is_acceptable`` communicates that, so
    the caller can show rejection reasons and let the user retry. Returns
    an HTTP error only for a hard validation failure: unsupported format
    (415), invalid/corrupted image content (400), oversized upload (413),
    or a ``session_id`` that isn't the caller's own (403).
    """
    try:
        session = await get_or_create_session_for_user(db, current_user, session_id)
    except SessionOwnershipError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "session_forbidden", "message": str(exc)},
        ) from exc

    try:
        return await ingest_image(
            db=db, settings=settings, session_id=str(session.id), upload=file
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
    current_user: User = Depends(get_current_user),
) -> VisualAnalysisResult:
    """Run the non-diagnostic visual-observation pipeline on a previously
    uploaded, quality-accepted image.

    Requires that ``analysis_id`` exists, belongs to the authenticated
    user, and its image both passed the Phase 2 quality gate and is
    still retained on disk. Returns a structured error (never a
    fabricated result) otherwise: 404 unknown analysis/missing image
    file, 403 someone else's analysis, 422 quality gate not passed, 409
    image not retained.
    """
    await _assert_owns_analysis(db, analysis_id, current_user)
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
    current_user: User = Depends(get_current_user),
) -> AnalysisDetailResponse:
    """Retrieve a previously created analysis -- never recomputes the
    quality gate or the vision pipeline. ``status`` explicitly represents
    every stage (quality rejected, ready for visual analysis, analyzing,
    completed, failed) rather than a client having to infer it;
    ``visual_analysis`` is ``None`` until ``status`` is ``"completed"``.
    Never exposes a server filesystem path. 404 for an unknown id, 403
    for one that exists but belongs to a different user.
    """
    await _assert_owns_analysis(db, analysis_id, current_user)
    try:
        return await get_analysis_detail(db, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "analysis_not_found", "message": str(exc)},
        ) from exc
