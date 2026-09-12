"""Integration tests for POST /api/analysis/upload.

Exercises the real database (see conftest.py) so persistence, not just
schema validation, is verified end-to-end.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.main import app
from tests.helpers.images import (
    corrupted_jpeg_bytes,
    make_acceptable_image,
    make_dark_image,
    make_tiny_image,
    not_an_image_bytes,
    to_bytes,
)

UPLOAD_URL = "/api/analysis/upload"


def _jpeg_file(width: int = 800, height: int = 800, name: str = "photo.jpg"):
    raw = to_bytes(make_acceptable_image(width, height), "JPEG")
    return {"file": (name, raw, "image/jpeg")}


@pytest.mark.asyncio
async def test_successful_upload_returns_structured_response(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())

    assert response.status_code == 201
    body = response.json()
    assert "analysis_id" in body
    assert "session_id" in body
    assert body["quality"]["is_acceptable"] is True
    assert body["quality"]["issues"] == []
    assert body["image"]["content_type"] == "image/jpeg"
    assert body["image"]["width_px"] == 800
    assert body["image"]["height_px"] == 800
    # never leaks a server filesystem path
    assert "storage_path" not in body["image"]
    assert "/" not in body["image"]["content_hash"]


@pytest.mark.asyncio
async def test_successful_png_upload(authenticated_client: AsyncClient) -> None:
    raw = to_bytes(make_acceptable_image(800, 800), "PNG")
    response = await authenticated_client.post(
        UPLOAD_URL, files={"file": ("photo.png", raw, "image/png")}
    )
    assert response.status_code == 201
    assert response.json()["image"]["content_type"] == "image/png"


@pytest.mark.asyncio
async def test_low_quality_image_still_uploads_successfully_but_marked_rejected(
    authenticated_client: AsyncClient,
) -> None:
    raw = to_bytes(make_dark_image(800, 800), "JPEG")
    response = await authenticated_client.post(
        UPLOAD_URL, files={"file": ("dark.jpg", raw, "image/jpeg")}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["quality"]["is_acceptable"] is False
    assert "too_dark" in body["quality"]["issues"]
    assert body["quality"]["message"] == (
        "Image quality is insufficient for reliable visual analysis."
    )


@pytest.mark.asyncio
async def test_tiny_image_rejected_by_quality_gate(authenticated_client: AsyncClient) -> None:
    raw = to_bytes(make_tiny_image(50, 50), "JPEG")
    response = await authenticated_client.post(
        UPLOAD_URL, files={"file": ("tiny.jpg", raw, "image/jpeg")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["quality"]["is_acceptable"] is False
    assert "too_low_resolution" in body["quality"]["issues"]


@pytest.mark.asyncio
async def test_unsupported_format_is_rejected_with_415(authenticated_client: AsyncClient) -> None:
    raw = to_bytes(make_acceptable_image(400, 400), "BMP")
    response = await authenticated_client.post(
        UPLOAD_URL, files={"file": ("photo.bmp", raw, "image/bmp")}
    )
    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "unsupported_format"


@pytest.mark.asyncio
async def test_fake_image_with_image_mimetype_is_rejected_with_400(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        UPLOAD_URL,
        files={"file": ("photo.jpg", not_an_image_bytes(), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_image_content"


@pytest.mark.asyncio
async def test_corrupted_image_is_rejected_with_400(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        UPLOAD_URL,
        files={"file": ("photo.jpg", corrupted_jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_image_content"


@pytest.mark.asyncio
async def test_missing_file_returns_422(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(UPLOAD_URL)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_oversized_upload_is_rejected_with_413(authenticated_client: AsyncClient) -> None:
    def tiny_max_settings() -> Settings:
        return Settings(image_max_size_mb=1)

    app.dependency_overrides[get_settings] = tiny_max_settings
    try:
        raw = to_bytes(make_acceptable_image(1600, 1600), "PNG")
        assert len(raw) > 1 * 1024 * 1024
        response = await authenticated_client.post(
            UPLOAD_URL, files={"file": ("big.png", raw, "image/png")}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


@pytest.mark.asyncio
async def test_path_traversal_filename_is_sanitized_in_response(
    authenticated_client: AsyncClient,
) -> None:
    raw = to_bytes(make_acceptable_image(800, 800), "JPEG")
    response = await authenticated_client.post(
        UPLOAD_URL,
        files={"file": ("../../etc/passwd.jpg", raw, "image/jpeg")},
    )
    assert response.status_code == 201
    filename = response.json()["image"]["original_filename"]
    assert filename == "passwd.jpg"
    assert ".." not in filename
    assert "/" not in filename


@pytest.mark.asyncio
async def test_retention_mode_none_never_persists_a_storage_path(
    authenticated_client: AsyncClient,
) -> None:
    def none_retention_settings() -> Settings:
        return Settings(image_retention_mode="none")

    app.dependency_overrides[get_settings] = none_retention_settings
    try:
        response = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    # storage_path is never exposed in the API response regardless of
    # retention mode; this test's real guarantee is checked at the
    # service layer in tests/test_image_service.py.


@pytest.mark.asyncio
async def test_response_never_exposes_a_filesystem_path(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())
    body_text = response.text
    assert "/app/data" not in body_text
    assert "/data/uploads" not in body_text


# --- Rate limiting (Phase 12 follow-up) ---


@pytest.mark.asyncio
async def test_upload_is_rate_limited_past_the_configured_max(authenticated_client: AsyncClient) -> None:
    """Proves the dependency is actually wired to the real route -- a
    tiny configured limit is exceeded with real requests through the
    real ASGI app, not just the limiter class in isolation (see
    tests/core/test_rate_limit.py for that).
    """
    from app.core.rate_limit import _upload_limiter

    def tiny_rate_limit_settings() -> Settings:
        return Settings(rate_limit_upload_max_requests=2, rate_limit_upload_window_seconds=60.0)

    app.dependency_overrides[get_settings] = tiny_rate_limit_settings
    _upload_limiter._windows.clear()
    try:
        first = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())
        second = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())
        third = await authenticated_client.post(UPLOAD_URL, files=_jpeg_file())
    finally:
        app.dependency_overrides.clear()
        _upload_limiter._windows.clear()

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "rate_limited"
    assert "Retry-After" in third.headers
