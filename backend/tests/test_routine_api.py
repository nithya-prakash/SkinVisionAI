"""Integration tests for POST /api/routine/analyze.

This endpoint is stateless by default -- no database is touched -- so
these tests don't need the real-DB `client` fixture's data to persist;
they still use it for a real ASGI request/response round trip. Phase 8
adds an opt-in ``persist`` flag (tested at the bottom of this file);
every test above that point predates and is unaffected by it.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

ANALYZE_URL = "/api/routine/analyze"


def _product(name, ingredients, category=None, time_of_day="unspecified"):
    return {
        "product_name": name,
        "raw_ingredients": ingredients,
        "category": category,
        "time_of_day": time_of_day,
    }


@pytest.mark.asyncio
async def test_routine_analyze_returns_structured_result(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={
            "products": [
                _product("Cleanser", "Water, Glycerin", "cleanser", "AM_AND_PM"),
                _product("Retinol Serum", "Retinol", "treatment", "PM"),
                _product("Acid Toner", "Glycolic Acid", "toner", "PM"),
                _product("Sunscreen", "Zinc Oxide", "sunscreen"),
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["products"]) == 4
    assert len(body["interactions"]) == 1
    assert body["interactions"][0]["severity"] == "caution"
    am_names = [s["product_name"] for s in body["suggested_am"]]
    pm_names = [s["product_name"] for s in body["suggested_pm"]]
    assert am_names == ["Cleanser", "Sunscreen"]
    assert pm_names == ["Cleanser", "Acid Toner", "Retinol Serum"]
    assert body["disclaimer"].startswith("SkinVision AI provides educational")


@pytest.mark.asyncio
async def test_routine_analyze_overlapping_actives(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={
            "products": [
                _product("A", "Retinol, Niacinamide"),
                _product("B", "Retinol, Hyaluronic Acid"),
            ]
        },
    )
    body = response.json()
    assert len(body["overlapping_actives"]) == 1
    assert body["overlapping_actives"][0]["ingredient"] == "retinol"


@pytest.mark.asyncio
async def test_routine_analyze_unscheduled_unknown_category(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL, json={"products": [_product("Mystery", "Water")]}
    )
    body = response.json()
    assert body["suggested_am"] == []
    assert body["suggested_pm"] == []
    assert len(body["unscheduled_products"]) == 1


@pytest.mark.asyncio
async def test_routine_analyze_rejects_empty_products_list(client: AsyncClient) -> None:
    response = await client.post(ANALYZE_URL, json={"products": []})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_routine_analyze_rejects_missing_ingredients(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"products": [{"product_name": "A", "raw_ingredients": ""}]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_routine_analyze_is_deterministic(client: AsyncClient) -> None:
    payload = {
        "products": [
            _product("Retinol Serum", "Retinol", "treatment", "PM"),
            _product("Acid Toner", "Glycolic Acid", "toner", "PM"),
        ]
    }
    first = await client.post(ANALYZE_URL, json=payload)
    second = await client.post(ANALYZE_URL, json=payload)
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_routine_analyze_never_exposes_internal_paths(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL, json={"products": [_product("A", "Water")]}
    )
    assert "/app/rules" not in response.text
    assert "/backend/rules" not in response.text


# --- Phase 8: opt-in persistence ---


@pytest.mark.asyncio
async def test_routine_analyze_without_persist_flag_returns_null_id(client: AsyncClient) -> None:
    response = await client.post(ANALYZE_URL, json={"products": [_product("A", "Retinol")]})
    assert response.status_code == 200
    assert response.json()["id"] is None


@pytest.mark.asyncio
async def test_routine_analyze_with_persist_true_returns_an_id(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL, json={"persist": True, "products": [_product("A", "Retinol")]}
    )
    assert response.status_code == 200
    assert response.json()["id"] is not None


@pytest.mark.asyncio
async def test_routine_analyze_persist_true_result_matches_non_persisted_result(
    client: AsyncClient,
) -> None:
    payload = {"products": [_product("A", "Retinol"), _product("B", "Glycolic Acid")]}
    without = await client.post(ANALYZE_URL, json=payload)

    with_persist = await client.post(ANALYZE_URL, json={**payload, "persist": True})

    without_body = without.json()
    with_body = with_persist.json()
    without_body.pop("id")
    with_body.pop("id")
    assert without_body == with_body
