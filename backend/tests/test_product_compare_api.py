"""Integration tests for POST /api/products/compare. Stateless by default
-- no database writes -- but exercised as a real ASGI request/response.
Phase 8 adds an opt-in ``persist`` flag (tested at the bottom of this
file); every test above that point predates and is unaffected by it.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

COMPARE_URL = "/api/products/compare"


def _payload(name_a, ingredients_a, name_b, ingredients_b):
    return {
        "product_a": {"name": name_a, "raw_ingredient_text": ingredients_a},
        "product_b": {"name": name_b, "raw_ingredient_text": ingredients_b},
    }


@pytest.mark.asyncio
async def test_compare_partially_overlapping_products(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        COMPARE_URL,
        json=_payload(
            "Product A", "Retinol, Niacinamide, Glycerin",
            "Product B", "Retinol, Salicylic Acid, Glycerin",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body["shared_ingredients"]) == {"retinol", "glycerin"}
    assert body["only_in_a"] == ["niacinamide"]
    assert body["only_in_b"] == ["salicylic_acid"]
    # Real shipped rule set: retinol+salicylic_acid (caution, cross-product)
    # AND retinol+niacinamide (informational, within product A) both fire.
    severities = {i["rule_id"]: i["severity"] for i in body["interactions"]}
    assert severities["retinol_salicylic_acid_caution"] == "caution"
    assert severities["retinol_niacinamide_informational"] == "informational"
    assert body["disclaimer"].startswith("SkinVision AI provides educational")


@pytest.mark.asyncio
async def test_compare_identical_products(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        COMPARE_URL, json=_payload("A", "Water, Niacinamide", "B", "Water, Niacinamide")
    )
    body = response.json()
    assert set(body["shared_ingredients"]) == {"water", "niacinamide"}
    assert body["only_in_a"] == []
    assert body["only_in_b"] == []


@pytest.mark.asyncio
async def test_compare_never_computes_a_score(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(COMPARE_URL, json=_payload("A", "Retinol", "B", "Water"))
    body_text = response.text.lower()
    for banned in ("score", "better_product", "winner"):
        assert banned not in body_text


@pytest.mark.asyncio
async def test_compare_rejects_missing_ingredient_text(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        COMPARE_URL,
        json={
            "product_a": {"name": "A", "raw_ingredient_text": ""},
            "product_b": {"name": "B", "raw_ingredient_text": "Water"},
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_compare_is_deterministic(authenticated_client: AsyncClient) -> None:
    payload = _payload("A", "Retinol, Glycolic Acid", "B", "Niacinamide")
    first = await authenticated_client.post(COMPARE_URL, json=payload)
    second = await authenticated_client.post(COMPARE_URL, json=payload)
    assert first.json() == second.json()


# --- Phase 8: opt-in persistence ---


@pytest.mark.asyncio
async def test_compare_without_persist_flag_returns_null_id(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(COMPARE_URL, json=_payload("A", "Retinol", "B", "Niacinamide"))
    assert response.status_code == 200
    assert response.json()["id"] is None


@pytest.mark.asyncio
async def test_compare_with_persist_true_returns_an_id(authenticated_client: AsyncClient) -> None:
    payload = _payload("A", "Retinol", "B", "Niacinamide")
    payload["persist"] = True
    response = await authenticated_client.post(COMPARE_URL, json=payload)
    assert response.status_code == 200
    assert response.json()["id"] is not None


@pytest.mark.asyncio
async def test_compare_persist_true_result_matches_non_persisted_result(
    authenticated_client: AsyncClient,
) -> None:
    payload = _payload("A", "Retinol, Niacinamide", "B", "Retinol, Salicylic Acid")
    without = await authenticated_client.post(COMPARE_URL, json=payload)

    payload["persist"] = True
    with_persist = await authenticated_client.post(COMPARE_URL, json=payload)

    without_body = without.json()
    with_body = with_persist.json()
    without_body.pop("id")
    with_body.pop("id")
    assert without_body == with_body
