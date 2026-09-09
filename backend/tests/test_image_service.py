"""Service-layer tests for app.services.image_service.ingest_image.

Covers what the API response intentionally never exposes: whether a file
was actually written to (or withheld from) disk under each retention mode.
Uses a real database session (see conftest.py / README) and a pytest
tmp_path for the upload directory so nothing touches real project files.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from sqlalchemy import select
from starlette.datastructures import Headers, UploadFile

from app.config import Settings
from app.database import AsyncSessionLocal
from app.models.image import ImageMetadata
from app.services.image_service import ingest_image
from tests.helpers.images import make_acceptable_image, to_bytes


def _settings(tmp_path: Path, retention_mode: str) -> Settings:
    return Settings(
        upload_directory=tmp_path / "uploads",
        image_retention_mode=retention_mode,
    )


def _upload_file(raw: bytes, filename: str = "photo.jpg") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(raw),
        filename=filename,
        headers=Headers({"content-type": "image/jpeg"}),
    )


@pytest.mark.asyncio
async def test_temporary_retention_writes_file_and_records_storage_path(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, "temporary")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        result = await ingest_image(
            db=db, settings=settings, session_id=None, upload=_upload_file(raw)
        )
        row = await db.get(ImageMetadata, result.image.id)

    assert row is not None
    assert row.storage_path is not None
    assert Path(row.storage_path).exists()
    assert Path(row.storage_path).is_relative_to(settings.upload_directory)


@pytest.mark.asyncio
async def test_none_retention_never_writes_a_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "none")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        result = await ingest_image(
            db=db, settings=settings, session_id=None, upload=_upload_file(raw)
        )
        row = await db.get(ImageMetadata, result.image.id)

    assert row is not None
    assert row.storage_path is None
    # The retention-mode="none" contract is "never touches disk" -- the
    # upload directory must not even have been created.
    assert not settings.upload_directory.exists()


@pytest.mark.asyncio
async def test_ingest_image_persists_quality_result_on_the_row(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "none")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        result = await ingest_image(
            db=db, settings=settings, session_id=None, upload=_upload_file(raw)
        )
        row = await db.get(ImageMetadata, result.image.id)

    assert row.quality_result is not None
    assert row.quality_result["is_acceptable"] is True


@pytest.mark.asyncio
async def test_ingest_image_creates_a_linked_skin_analysis_row(tmp_path: Path) -> None:
    from app.models.analysis import SkinAnalysis

    settings = _settings(tmp_path, "none")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        result = await ingest_image(
            db=db, settings=settings, session_id=None, upload=_upload_file(raw)
        )
        analysis = await db.get(SkinAnalysis, result.analysis_id)

    assert analysis is not None
    assert analysis.image_id == result.image.id
    assert analysis.status == "image_uploaded"


@pytest.mark.asyncio
async def test_ingest_image_reuses_an_existing_valid_session(tmp_path: Path) -> None:
    from app.models.session import UserSession

    settings = _settings(tmp_path, "none")
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")

    async with AsyncSessionLocal() as db:
        existing = UserSession()
        db.add(existing)
        await db.flush()
        await db.commit()
        existing_id = existing.id

    async with AsyncSessionLocal() as db:
        result = await ingest_image(
            db=db,
            settings=settings,
            session_id=str(existing_id),
            upload=_upload_file(raw),
        )

    assert result.session_id == existing_id

    async with AsyncSessionLocal() as db:
        count = await db.scalar(
            select(UserSession).where(UserSession.id == existing_id).limit(1)
        )
        assert count is not None
