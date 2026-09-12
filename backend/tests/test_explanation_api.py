"""Integration tests for POST /api/explanations/{product,compare,routine}.

Stateless -- no database writes. Uses the real ASGI app with the LLM
provider dependency overridden to a FakeLLMProvider, so these tests need
no API key and no network.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.api.explanations import _provider
from app.llm.base import LLMTimeoutError
from app.llm.provider import FakeLLMProvider
from app.llm.schemas import ExplanationLLMOutput
from app.main import app


@pytest.fixture(autouse=True)
def _default_fake_provider():
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider()
    yield
    app.dependency_overrides.pop(_provider, None)


@pytest.mark.asyncio
async def test_explain_product_endpoint(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/explanations/product",
        json={"name": "Retinol Serum", "raw_ingredient_text": "Retinol, Glycolic Acid"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["explanation_status"] == "available"
    assert body["explanation"] is not None
    assert len(body["analysis"]["interactions"]) == 1
    assert body["explanation"]["disclaimer"].startswith("SkinVision AI provides educational")


@pytest.mark.asyncio
async def test_explain_compare_endpoint(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/explanations/compare",
        json={
            "product_a": {"name": "A", "raw_ingredient_text": "Retinol, Niacinamide"},
            "product_b": {"name": "B", "raw_ingredient_text": "Retinol, Salicylic Acid"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["explanation_status"] == "available"
    assert set(body["analysis"]["shared_ingredients"]) == {"retinol"}


@pytest.mark.asyncio
async def test_explain_routine_endpoint(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/explanations/routine",
        json={
            "products": [
                {"product_name": "A", "raw_ingredients": "Retinol"},
                {"product_name": "B", "raw_ingredients": "Glycolic Acid"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["explanation_status"] == "available"
    assert len(body["analysis"]["interactions"]) == 1
    assert len(body["explanation"]["interactions_explained"]) == 1


@pytest.mark.asyncio
async def test_explain_routine_llm_unavailable_still_returns_analysis(authenticated_client: AsyncClient) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        raise_error=LLMTimeoutError("simulated")
    )
    response = await authenticated_client.post(
        "/api/explanations/routine",
        json={"products": [{"product_name": "A", "raw_ingredients": "Retinol, Glycolic Acid"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["explanation_status"] == "unavailable"
    assert body["explanation"] is None
    assert body["explanation_error"] is not None
    # Deterministic analysis is still fully present.
    assert len(body["analysis"]["interactions"]) == 1


@pytest.mark.asyncio
async def test_explain_routine_hallucinating_provider_rejected(authenticated_client: AsyncClient) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        fixed_response=ExplanationLLMOutput(summary="This routine is completely safe.")
    )
    response = await authenticated_client.post(
        "/api/explanations/routine",
        json={"products": [{"product_name": "A", "raw_ingredients": "Water"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["explanation_status"] == "unavailable"
    assert body["explanation"] is None


@pytest.mark.asyncio
async def test_explain_endpoints_never_expose_api_keys_or_internals(authenticated_client: AsyncClient) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        raise_error=LLMTimeoutError("sk-super-secret-leak-test")
    )
    response = await authenticated_client.post(
        "/api/explanations/product",
        json={"name": "A", "raw_ingredient_text": "Water"},
    )
    assert "sk-super-secret-leak-test" not in response.text


@pytest.mark.asyncio
async def test_explain_product_rejects_missing_ingredients(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/api/explanations/product", json={"name": "A", "raw_ingredient_text": ""}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_explain_routine_is_deterministic(authenticated_client: AsyncClient) -> None:
    payload = {"products": [{"product_name": "A", "raw_ingredients": "Retinol, Glycolic Acid"}]}
    first = await authenticated_client.post("/api/explanations/routine", json=payload)
    second = await authenticated_client.post("/api/explanations/routine", json=payload)
    assert first.json() == second.json()


# --- Phase 8: opt-in persistence, wired through the explanation endpoints
# (the ones the frontend actually calls) rather than only the raw
# deterministic-only endpoints. ---


@pytest.mark.asyncio
async def test_explain_routine_without_persist_returns_null_analysis_id(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/explanations/routine",
        json={"products": [{"product_name": "A", "raw_ingredients": "Retinol"}]},
    )
    assert response.json()["analysis"]["id"] is None


@pytest.mark.asyncio
async def test_explain_routine_with_persist_true_returns_an_analysis_id(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/explanations/routine",
        json={"persist": True, "products": [{"product_name": "A", "raw_ingredients": "Retinol"}]},
    )
    assert response.status_code == 200
    assert response.json()["analysis"]["id"] is not None


@pytest.mark.asyncio
async def test_explain_compare_with_persist_true_returns_an_analysis_id(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.post(
        "/api/explanations/compare",
        json={
            "persist": True,
            "product_a": {"name": "A", "raw_ingredient_text": "Retinol"},
            "product_b": {"name": "B", "raw_ingredient_text": "Niacinamide"},
        },
    )
    assert response.status_code == 200
    assert response.json()["analysis"]["id"] is not None
