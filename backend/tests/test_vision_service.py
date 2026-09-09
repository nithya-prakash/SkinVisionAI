"""Service-layer tests for app.services.vision_service.analyze_visual_features.

Uses the real database (see conftest.py) and Phase 2's real ingest_image to
set up fixtures -- verifying Phase 3 actually reuses Phase 2's persisted
quality-gate result rather than re-deriving or duplicating it.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.config import Settings
from app.database import AsyncSessionLocal
from app.models.analysis import SkinAnalysis
from app.models.image import ImageMetadata
from app.services.image_service import ingest_image
from app.services.vision_service import VisualAnalysisError, analyze_visual_features
from tests.helpers.images import make_acceptable_image, make_dark_image, to_bytes


def _settings(tmp_path: Path, retention_mode: str = "temporary") -> Settings:
    return Settings(upload_directory=tmp_path / "uploads", image_retention_mode=retention_mode)


def _upload_file(raw: bytes, filename: str = "photo.jpg") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(raw), filename=filename, headers=Headers({"content-type": "image/jpeg"})
    )


@pytest.mark.asyncio
async def test_successful_visual_analysis_persists_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        upload = await ingest_image(db=db, settings=settings, session_id=None, upload=_upload_file(raw))
        result = await analyze_visual_features(
            db=db, settings=settings, analysis_id=upload.analysis_id
        )

    assert len(result.observations) == 5
    assert result.analysis_id == upload.analysis_id

    async with AsyncSessionLocal() as db:
        row = await db.get(SkinAnalysis, upload.analysis_id)

    assert row.status == "completed"
    assert row.visual_observations is not None
    assert len(row.visual_observations) == 5
    assert row.structured_response is not None
    assert row.structured_response["region_used"] in ("detected_face", "center_crop_fallback")


@pytest.mark.asyncio
async def test_quality_gate_not_passed_raises_422(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = to_bytes(make_dark_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        upload = await ingest_image(db=db, settings=settings, session_id=None, upload=_upload_file(raw))
        assert upload.quality.is_acceptable is False  # sanity check on the fixture

        with pytest.raises(VisualAnalysisError) as exc_info:
            await analyze_visual_features(db=db, settings=settings, analysis_id=upload.analysis_id)

    assert exc_info.value.code == "quality_gate_not_passed"
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_image_not_retained_raises_409(tmp_path: Path) -> None:
    settings = _settings(tmp_path, retention_mode="none")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        upload = await ingest_image(db=db, settings=settings, session_id=None, upload=_upload_file(raw))

        with pytest.raises(VisualAnalysisError) as exc_info:
            await analyze_visual_features(db=db, settings=settings, analysis_id=upload.analysis_id)

    assert exc_info.value.code == "image_not_retained"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_unknown_analysis_id_raises_404(tmp_path: Path) -> None:
    import uuid

    settings = _settings(tmp_path)
    async with AsyncSessionLocal() as db:
        with pytest.raises(VisualAnalysisError) as exc_info:
            await analyze_visual_features(db=db, settings=settings, analysis_id=uuid.uuid4())

    assert exc_info.value.code == "analysis_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_image_file_on_disk_raises_404(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        upload = await ingest_image(db=db, settings=settings, session_id=None, upload=_upload_file(raw))
        image_row = await db.get(ImageMetadata, upload.image.id)
        Path(image_row.storage_path).unlink()  # simulate the file having been removed

        with pytest.raises(VisualAnalysisError) as exc_info:
            await analyze_visual_features(db=db, settings=settings, analysis_id=upload.analysis_id)

        # Phase 8: a failure must leave the row in an explicit terminal
        # "failed" state, never silently stuck at its prior status.
        analysis_row = await db.get(SkinAnalysis, upload.analysis_id)
        assert analysis_row.status == "failed"

    assert exc_info.value.code == "image_file_missing"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_repeated_analysis_is_deterministic(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        upload = await ingest_image(db=db, settings=settings, session_id=None, upload=_upload_file(raw))
        first = await analyze_visual_features(
            db=db, settings=settings, analysis_id=upload.analysis_id
        )
        second = await analyze_visual_features(
            db=db, settings=settings, analysis_id=upload.analysis_id
        )

    first_scores = [(o.feature, o.score, o.level) for o in first.observations]
    second_scores = [(o.feature, o.score, o.level) for o in second.observations]
    assert first_scores == second_scores
    assert first.region_used == second.region_used
