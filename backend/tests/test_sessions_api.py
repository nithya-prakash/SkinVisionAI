"""Integration tests for the session endpoints (Phase 8):
``POST /api/sessions``, ``GET /api/sessions/{id}``,
``GET /api/sessions/{id}/analyses``, ``GET /api/sessions/{id}/chats``.
Phase 9 adds ``.../products``, ``.../routine-analyses``, ``.../comparisons``
(the endpoints History needed).

Exercises the real database, consistent with this project's testing
convention.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.api.agent import _provider
from app.llm.base import AgentLLMResponse
from app.llm.provider import FakeLLMProvider
from app.main import app
from tests.helpers.images import make_acceptable_image, to_bytes


def _final(answer: str) -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=None,
        final_answer=AgentFinalAnswerLLMOutput(answer=answer, key_points=[], limitations=[]),
    )


@pytest.mark.asyncio
async def test_create_session(client: AsyncClient) -> None:
    response = await client.post("/api/sessions")
    assert response.status_code == 201
    body = response.json()
    assert uuid.UUID(body["id"])
    assert "created_at" in body


@pytest.mark.asyncio
async def test_retrieve_existing_session(client: AsyncClient) -> None:
    created = (await client.post("/api/sessions")).json()
    response = await client.get(f"/api/sessions/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_retrieve_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


@pytest.mark.asyncio
async def test_unknown_session_never_silently_created_on_read(client: AsyncClient) -> None:
    """A GET naming an unknown id must 404, not fabricate a new session
    (unlike write paths, which legitimately create one when none is
    given) -- see app.services.session_service.get_session's docstring.
    """
    unknown_id = uuid.uuid4()
    response = await client.get(f"/api/sessions/{unknown_id}")
    assert response.status_code == 404
    # Confirm it really wasn't created behind the scenes either.
    second = await client.get(f"/api/sessions/{unknown_id}")
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_list_analyses_for_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}/analyses")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_chats_for_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}/chats")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_analyses_empty_for_a_fresh_session(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    response = await client.get(f"/api/sessions/{session_id}/analyses")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["analyses"] == []


@pytest.mark.asyncio
async def test_list_analyses_includes_an_uploaded_image(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    upload = await client.post(
        "/api/analysis/upload",
        files={"file": ("photo.jpg", to_bytes(make_acceptable_image(800, 800), "JPEG"), "image/jpeg")},
        data={"session_id": session_id},
    )
    assert upload.status_code == 201
    analysis_id = upload.json()["analysis_id"]

    response = await client.get(f"/api/sessions/{session_id}/analyses")
    body = response.json()
    assert len(body["analyses"]) == 1
    assert body["analyses"][0]["id"] == analysis_id
    assert body["analyses"][0]["status"] == "ready_for_visual_analysis"


@pytest.mark.asyncio
async def test_list_chats_empty_for_a_fresh_session(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    response = await client.get(f"/api/sessions/{session_id}/chats")
    assert response.status_code == 200
    assert response.json()["chats"] == []


@pytest.mark.asyncio
async def test_list_chats_includes_a_chat_with_message_count(client: AsyncClient) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        agent_script=[_final("Hello!")]
    )
    try:
        session_id = (await client.post("/api/sessions")).json()["id"]
        chat = await client.post(
            "/api/agent/chat", json={"message": "Hi", "session_id": session_id}
        )
        assert chat.status_code == 200
        chat_session_id = chat.json()["chat_session_id"]

        response = await client.get(f"/api/sessions/{session_id}/chats")
        body = response.json()
        assert len(body["chats"]) == 1
        assert body["chats"][0]["id"] == chat_session_id
        assert body["chats"][0]["message_count"] == 2  # user + assistant
    finally:
        app.dependency_overrides.pop(_provider, None)


# --- Phase 9: products / routine-analyses / comparisons ---


@pytest.mark.asyncio
async def test_list_products_for_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}/products")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_routine_analyses_for_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}/routine-analyses")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_comparisons_for_unknown_session_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid.uuid4()}/comparisons")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_products_empty_for_a_fresh_session(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    response = await client.get(f"/api/sessions/{session_id}/products")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["products"] == []


@pytest.mark.asyncio
async def test_list_products_includes_an_analyzed_product(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    analyze = await client.post(
        "/api/products/analyze",
        json={
            "session_id": session_id,
            "name": "Retinol Serum",
            "raw_ingredient_text": "Retinol, Glycolic Acid",
        },
    )
    assert analyze.status_code == 201
    product_id = analyze.json()["product_id"]

    response = await client.get(f"/api/sessions/{session_id}/products")
    body = response.json()
    assert len(body["products"]) == 1
    assert body["products"][0]["id"] == product_id
    assert body["products"][0]["name"] == "Retinol Serum"
    assert body["products"][0]["interaction_count"] == 1
    assert body["products"][0]["unknown_ingredient_count"] == 0


@pytest.mark.asyncio
async def test_list_routine_analyses_empty_for_a_fresh_session(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    response = await client.get(f"/api/sessions/{session_id}/routine-analyses")
    assert response.status_code == 200
    assert response.json()["routine_analyses"] == []


@pytest.mark.asyncio
async def test_list_routine_analyses_only_includes_persisted_ones(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]

    # Not persisted -- must not appear.
    not_persisted = await client.post(
        "/api/routine/analyze",
        json={"session_id": session_id, "products": [{"product_name": "A", "raw_ingredients": "Water"}]},
    )
    assert not_persisted.json()["id"] is None

    persisted = await client.post(
        "/api/routine/analyze",
        json={
            "session_id": session_id,
            "persist": True,
            "products": [
                {"product_name": "A", "raw_ingredients": "Retinol"},
                {"product_name": "B", "raw_ingredients": "Glycolic Acid"},
            ],
        },
    )
    record_id = persisted.json()["id"]
    assert record_id is not None

    response = await client.get(f"/api/sessions/{session_id}/routine-analyses")
    body = response.json()
    assert len(body["routine_analyses"]) == 1
    assert body["routine_analyses"][0]["id"] == record_id
    assert body["routine_analyses"][0]["product_count"] == 2
    assert body["routine_analyses"][0]["interaction_count"] == 1


@pytest.mark.asyncio
async def test_list_comparisons_empty_for_a_fresh_session(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]
    response = await client.get(f"/api/sessions/{session_id}/comparisons")
    assert response.status_code == 200
    assert response.json()["comparisons"] == []


@pytest.mark.asyncio
async def test_list_comparisons_only_includes_persisted_ones(client: AsyncClient) -> None:
    session_id = (await client.post("/api/sessions")).json()["id"]

    persisted = await client.post(
        "/api/products/compare",
        json={
            "session_id": session_id,
            "persist": True,
            "product_a": {"name": "Product A", "raw_ingredient_text": "Retinol"},
            "product_b": {"name": "Product B", "raw_ingredient_text": "Niacinamide"},
        },
    )
    record_id = persisted.json()["id"]
    assert record_id is not None

    response = await client.get(f"/api/sessions/{session_id}/comparisons")
    body = response.json()
    assert len(body["comparisons"]) == 1
    assert body["comparisons"][0]["id"] == record_id
    assert body["comparisons"][0]["product_a_name"] == "Product A"
    assert body["comparisons"][0]["product_b_name"] == "Product B"
