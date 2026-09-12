"""Tests for app.core.image_cleanup.cleanup_expired_images.

Uses a real database session (see conftest.py / README) and a pytest
tmp_path for on-disk files, exactly like tests/test_image_service.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import Settings
from app.core.image_cleanup import cleanup_expired_images
from app.database import AsyncSessionLocal
from app.models.image import ImageMetadata
from tests.helpers.auth import make_user_and_session


def _settings(ttl_hours: float = 24.0) -> Settings:
    return Settings(image_retention_ttl_hours=ttl_hours)


async def _make_image(db, tmp_path: Path, *, age_hours: float, write_file: bool = True) -> ImageMetadata:
    _, session = await make_user_and_session(db)
    path = tmp_path / f"{age_hours}.jpg"
    if write_file:
        path.write_bytes(b"fake-jpeg-bytes")
    row = ImageMetadata(
        session_id=session.id,
        storage_path=str(path),
        content_hash="deadbeef",
        original_filename="photo.jpg",
        content_type="image/jpeg",
        width_px=800,
        height_px=800,
        size_bytes=15,
        quality_result=None,
        created_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
    )
    db.add(row)
    await db.flush()
    return row


@pytest.mark.asyncio
async def test_expired_image_file_deleted_and_storage_path_cleared(tmp_path: Path) -> None:
    async with AsyncSessionLocal() as db:
        row = await _make_image(db, tmp_path, age_hours=48)
        path = Path(row.storage_path)

        cleaned = await cleanup_expired_images(db, _settings(ttl_hours=24))

        assert cleaned == 1
        assert not path.exists()
        refreshed = await db.get(ImageMetadata, row.id)
        assert refreshed.storage_path is None


@pytest.mark.asyncio
async def test_fresh_image_is_left_untouched(tmp_path: Path) -> None:
    async with AsyncSessionLocal() as db:
        row = await _make_image(db, tmp_path, age_hours=1)
        path = Path(row.storage_path)

        cleaned = await cleanup_expired_images(db, _settings(ttl_hours=24))

        assert cleaned == 0
        assert path.exists()
        refreshed = await db.get(ImageMetadata, row.id)
        assert refreshed.storage_path == str(path)


@pytest.mark.asyncio
async def test_already_null_storage_path_is_never_selected(tmp_path: Path) -> None:
    async with AsyncSessionLocal() as db:
        _, session = await make_user_and_session(db)
        row = ImageMetadata(
            session_id=session.id,
            storage_path=None,
            content_hash="deadbeef",
            original_filename="photo.jpg",
            content_type="image/jpeg",
            width_px=800,
            height_px=800,
            size_bytes=15,
            quality_result=None,
            created_at=datetime.now(timezone.utc) - timedelta(hours=999),
        )
        db.add(row)
        await db.flush()

        cleaned = await cleanup_expired_images(db, _settings(ttl_hours=24))

        assert cleaned == 0


@pytest.mark.asyncio
async def test_expired_row_with_file_already_missing_still_gets_cleaned(tmp_path: Path) -> None:
    async with AsyncSessionLocal() as db:
        row = await _make_image(db, tmp_path, age_hours=48, write_file=False)

        cleaned = await cleanup_expired_images(db, _settings(ttl_hours=24))

        assert cleaned == 1
        refreshed = await db.get(ImageMetadata, row.id)
        assert refreshed.storage_path is None


@pytest.mark.asyncio
async def test_zero_ttl_treats_everything_as_expired(tmp_path: Path) -> None:
    # ttl_hours=0 makes every already-existing row in the shared test
    # database "expired" too (created_at < now), not just this test's own
    # row -- so this asserts the specific row was cleaned, not an exact
    # global count, matching every other test in this file's pattern.
    async with AsyncSessionLocal() as db:
        row = await _make_image(db, tmp_path, age_hours=0.01)

        cleaned = await cleanup_expired_images(db, _settings(ttl_hours=0))

        assert cleaned >= 1
        refreshed = await db.get(ImageMetadata, row.id)
        assert refreshed.storage_path is None
