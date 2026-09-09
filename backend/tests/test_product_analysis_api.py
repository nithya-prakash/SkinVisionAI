"""Integration tests for POST /api/products/analyze.

Exercises the real database end-to-end (not mocks).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

ANALYZE_URL = "/api/products/analyze"


@pytest.mark.asyncio
async def test_analyze_simple_product_returns_structured_response(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={
            "name": "Gentle Hydrating Serum",
            "category": "serum",
            "raw_ingredient_text": "Water, Niacinamide, Glycerin, Panthenol",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Gentle Hydrating Serum"
    assert body["category"] == "serum"
    compat = body["compatibility"]
    assert len(compat["ingredients"]) == 4
    assert all(ing["matched"] for ing in compat["ingredients"])
    assert compat["interactions"] == []
    assert compat["unknown_ingredients"] == []
    assert compat["disclaimer"].startswith("SkinVision AI provides educational")


@pytest.mark.asyncio
async def test_analyze_product_surfaces_caution_interaction(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"name": "Retinol Serum", "raw_ingredient_text": "Retinol, Glycolic Acid"},
    )

    assert response.status_code == 201
    interactions = response.json()["compatibility"]["interactions"]
    assert len(interactions) == 1
    interaction = interactions[0]
    assert interaction["severity"] == "caution"
    assert interaction["source"] == "Cleveland Clinic"
    assert interaction["source_url"].startswith("https://")
    assert interaction["rule_id"] == "retinol_glycolic_acid_caution"


@pytest.mark.asyncio
async def test_analyze_product_reverse_ingredient_order_same_interaction(
    client: AsyncClient,
) -> None:
    forward = await client.post(
        ANALYZE_URL,
        json={"name": "A", "raw_ingredient_text": "Retinol, Salicylic Acid"},
    )
    reverse = await client.post(
        ANALYZE_URL,
        json={"name": "B", "raw_ingredient_text": "Salicylic Acid, Retinol"},
    )

    forward_rule_id = forward.json()["compatibility"]["interactions"][0]["rule_id"]
    reverse_rule_id = reverse.json()["compatibility"]["interactions"][0]["rule_id"]
    assert forward_rule_id == reverse_rule_id


@pytest.mark.asyncio
async def test_analyze_product_reports_unknown_ingredients(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"name": "Mystery Cream", "raw_ingredient_text": "Water, NovelComplexXYZ"},
    )

    body = response.json()["compatibility"]
    assert "NovelComplexXYZ" in body["unknown_ingredients"]
    unknown_entry = next(i for i in body["ingredients"] if i["raw_text"] == "NovelComplexXYZ")
    assert unknown_entry["matched"] is False
    assert unknown_entry["normalized_name"] is None


@pytest.mark.asyncio
async def test_analyze_product_ambiguous_alias_is_not_guessed(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"name": "Retinoid Cream", "raw_ingredient_text": "Vitamin A, Water"},
    )

    ingredients = response.json()["compatibility"]["ingredients"]
    vitamin_a_entry = next(i for i in ingredients if i["raw_text"] == "Vitamin A")
    assert vitamin_a_entry["matched"] is False
    assert vitamin_a_entry["ambiguous"] is True
    assert "retinol" in vitamin_a_entry["candidates"]


@pytest.mark.asyncio
async def test_analyze_product_duplicate_ingredients_no_duplicate_findings(
    client: AsyncClient,
) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={
            "name": "Duplicate Test",
            "raw_ingredient_text": "Niacinamide, Niacinamide, Retinol",
        },
    )

    compat = response.json()["compatibility"]
    assert len(compat["interactions"]) == 1
    assert len(compat["ingredients"]) == 3


@pytest.mark.asyncio
async def test_analyze_product_rejects_empty_name(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL, json={"name": "", "raw_ingredient_text": "Water"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_product_rejects_empty_ingredient_text(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL, json={"name": "Test", "raw_ingredient_text": ""}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_product_rejects_unknown_category(client: AsyncClient) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"name": "Test", "category": "miracle_potion", "raw_ingredient_text": "Water"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_product_response_never_says_safe_for_unknown(
    client: AsyncClient,
) -> None:
    response = await client.post(
        ANALYZE_URL,
        json={"name": "Mystery Serum", "raw_ingredient_text": "NovelComplexXYZ"},
    )
    body_text = response.text.lower()
    assert '"safe"' not in body_text
    # a bare "safe" substring check would also flag "unsafe"-style words; the
    # unknown-ingredient path should not claim safety at all
    assert "is safe" not in body_text
