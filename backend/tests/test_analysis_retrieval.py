"""Integration tests for GET /api/analysis/{id} (Phase 8).

Exercises the real database and the real upload/visual-analysis
endpoints end-to-end, consistent with this project's testing convention.
Never recomputes anything -- these tests specifically assert that the
retrieved data matches what was already persisted, not a fresh
computation.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.main import app
from tests.helpers.images import make_acceptable_image, make_dark_image, to_bytes


async def _upload(authenticated_client: AsyncClient, image_bytes: bytes, session_id: str | None = None) -> dict:
    data = {"session_id": session_id} if session_id else {}
    response = await authenticated_client.post(
        "/api/analysis/upload",
        files={"file": ("photo.jpg", image_bytes, "image/jpeg")},
        data=data,
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_get_analysis_linked_to_its_session(authenticated_client: AsyncClient) -> None:
    session_id = (await authenticated_client.post("/api/sessions")).json()["id"]
    upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"), session_id)

    response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == upload["analysis_id"]
    assert body["session_id"] == session_id


@pytest.mark.asyncio
async def test_get_analysis_ready_for_visual_analysis(authenticated_client: AsyncClient) -> None:
    upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    body = response.json()
    assert body["status"] == "ready_for_visual_analysis"
    assert body["visual_analysis"] is None
    assert body["image"]["quality_result"]["is_acceptable"] is True


@pytest.mark.asyncio
async def test_get_analysis_quality_rejected(authenticated_client: AsyncClient) -> None:
    upload = await _upload(authenticated_client, to_bytes(make_dark_image(800, 800), "JPEG"))
    response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    body = response.json()
    assert body["status"] == "quality_rejected"
    assert body["visual_analysis"] is None


@pytest.mark.asyncio
async def test_get_analysis_completed_after_visual_analysis(authenticated_client: AsyncClient) -> None:
    upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    ran = await authenticated_client.post(f"/api/analysis/{upload['analysis_id']}/visual-analysis")
    assert ran.status_code == 200

    response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    body = response.json()
    assert body["status"] == "completed"
    assert body["visual_analysis"] is not None
    assert len(body["visual_analysis"]["observations"]) == 5
    # Matches what the POST endpoint itself returned -- retrieval, not recomputation.
    assert body["visual_analysis"]["observations"] == ran.json()["observations"]


@pytest.mark.asyncio
async def test_get_analysis_unknown_id_returns_404(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get(f"/api/analysis/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_found"


@pytest.mark.asyncio
async def test_get_analysis_repeated_retrieval_is_stable(authenticated_client: AsyncClient) -> None:
    upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    await authenticated_client.post(f"/api/analysis/{upload['analysis_id']}/visual-analysis")

    first = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    second = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    assert first.json()["visual_analysis"] == second.json()["visual_analysis"]
    assert first.json()["status"] == second.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_analysis_never_exposes_a_filesystem_path(authenticated_client: AsyncClient) -> None:
    upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    await authenticated_client.post(f"/api/analysis/{upload['analysis_id']}/visual-analysis")
    response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    body_text = response.text
    assert "/app/data" not in body_text
    assert "/data/uploads" not in body_text
    assert "storage_path" not in body_text


@pytest.mark.asyncio
async def test_get_analysis_invalid_id_format_returns_422(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/api/analysis/not-a-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_analysis_reports_failed_after_a_pipeline_failure(
    authenticated_client: AsyncClient, tmp_path
) -> None:
    """Phase 8: a visual-analysis failure must be reflected as an
    explicit "failed" status on retrieval, not left at whatever status
    preceded it.
    """

    def custom_settings() -> Settings:
        return Settings(upload_directory=tmp_path / "uploads")

    app.dependency_overrides[get_settings] = custom_settings
    try:
        upload = await _upload(authenticated_client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
        # Simulate the stored file having been removed out from under it.
        stored_files = list((tmp_path / "uploads").glob("*"))
        assert len(stored_files) == 1
        stored_files[0].unlink()

        ran = await authenticated_client.post(f"/api/analysis/{upload['analysis_id']}/visual-analysis")
        assert ran.status_code == 404

        response = await authenticated_client.get(f"/api/analysis/{upload['analysis_id']}")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.json()["status"] == "failed"
    assert response.json()["visual_analysis"] is None
