"""Integration tests for POST /api/analysis/{analysis_id}/visual-analysis.

Exercises the real database and the real upload endpoint end-to-end (not
mocks), consistent with this project's testing convention.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.config import Settings, get_settings
from app.main import app
from tests.helpers.images import make_acceptable_image, make_dark_image, make_tiny_image, to_bytes

UPLOAD_URL = "/api/analysis/upload"


def _visual_analysis_url(analysis_id: str) -> str:
    return f"/api/analysis/{analysis_id}/visual-analysis"


async def _upload(client: AsyncClient, image_bytes: bytes, filename: str = "photo.jpg") -> dict:
    response = await client.post(UPLOAD_URL, files={"file": (filename, image_bytes, "image/jpeg")})
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_visual_analysis_on_accepted_image_returns_structured_result(
    client: AsyncClient,
) -> None:
    upload = await _upload(client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    assert upload["quality"]["is_acceptable"] is True

    response = await client.post(_visual_analysis_url(upload["analysis_id"]))

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_id"] == upload["analysis_id"]
    assert body["image_id"] == upload["image"]["id"]
    assert len(body["observations"]) == 5
    feature_names = {obs["feature"] for obs in body["observations"]}
    assert feature_names == {
        "redness",
        "visible_texture",
        "shine_oiliness",
        "uneven_tone",
        "visible_spots_marks",
    }
    assert "dryness" not in feature_names
    assert body["region_used"] in ("detected_face", "center_crop_fallback")
    assert body["disclaimer"].startswith("SkinVision AI provides educational")
    assert len(body["limitations"]) >= 1


@pytest.mark.asyncio
async def test_visual_analysis_response_contains_no_diagnostic_language(
    client: AsyncClient,
) -> None:
    """Guards the *content* fields specifically -- the disclaimer field is
    expected (and required) to mention "diagnosis" as part of stating that
    this system does not provide one; it's excluded from this check.
    """
    upload = await _upload(client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    response = await client.post(_visual_analysis_url(upload["analysis_id"]))
    body = response.json()

    content_text = " ".join(
        [
            *(obs["note"] or "" for obs in body["observations"]),
            *body["limitations"],
        ]
    ).lower()
    for banned in ("acne", "rosacea", "eczema", "melanoma", "diagnos", "skin_health_score"):
        assert banned not in content_text
    assert "skin_health_score" not in response.text


@pytest.mark.asyncio
async def test_visual_analysis_rejects_low_quality_image_with_422(client: AsyncClient) -> None:
    upload = await _upload(client, to_bytes(make_dark_image(800, 800), "JPEG"))
    assert upload["quality"]["is_acceptable"] is False

    response = await client.post(_visual_analysis_url(upload["analysis_id"]))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "quality_gate_not_passed"


@pytest.mark.asyncio
async def test_visual_analysis_rejects_tiny_image_with_422(client: AsyncClient) -> None:
    upload = await _upload(client, to_bytes(make_tiny_image(50, 50), "JPEG"))
    response = await client.post(_visual_analysis_url(upload["analysis_id"]))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_visual_analysis_unknown_analysis_id_returns_404(client: AsyncClient) -> None:
    response = await client.post(_visual_analysis_url(str(uuid.uuid4())))
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_found"


@pytest.mark.asyncio
async def test_visual_analysis_invalid_analysis_id_format_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(_visual_analysis_url("not-a-uuid"))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_visual_analysis_never_exposes_a_filesystem_path(client: AsyncClient) -> None:
    upload = await _upload(client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
    response = await client.post(_visual_analysis_url(upload["analysis_id"]))
    body_text = response.text
    assert "/app/data" not in body_text
    assert "/data/uploads" not in body_text


@pytest.mark.asyncio
async def test_visual_analysis_rejects_when_image_was_not_retained(client: AsyncClient) -> None:
    def none_retention_settings() -> Settings:
        return Settings(image_retention_mode="none")

    app.dependency_overrides[get_settings] = none_retention_settings
    try:
        upload = await _upload(client, to_bytes(make_acceptable_image(800, 800), "JPEG"))
        response = await client.post(_visual_analysis_url(upload["analysis_id"]))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "image_not_retained"


@pytest.mark.asyncio
async def test_visual_analysis_is_deterministic_across_repeated_calls(
    client: AsyncClient,
) -> None:
    upload = await _upload(client, to_bytes(make_acceptable_image(800, 800), "JPEG"))

    first = await client.post(_visual_analysis_url(upload["analysis_id"]))
    second = await client.post(_visual_analysis_url(upload["analysis_id"]))

    first_body = first.json()
    second_body = second.json()
    assert [
        (o["feature"], o["score"], o["level"]) for o in first_body["observations"]
    ] == [(o["feature"], o["score"], o["level"]) for o in second_body["observations"]]
