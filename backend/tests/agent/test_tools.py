"""Tests for app.agent.tools: each tool wraps an existing deterministic
engine and returns the same result the engine itself would, reachable
only through ``execute_tool``/the registry (Pydantic-validated input).
"""
from __future__ import annotations

from app.agent.registry import execute_tool
from app.agent.tools import build_tool_registry
from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.normalizer import normalize_ingredient
from app.ingredients.rules import get_rule_set
from app.products.comparator import compare_products
from app.routine.analyzer import analyze_routine
from app.schemas.product import ProductCompareItem, ProductCompareRequest
from app.schemas.routine import RoutineAnalysisRequest, RoutineProductInput


def test_check_ingredient_compatibility_tool_matches_engine_output() -> None:
    registry = build_tool_registry()
    result = execute_tool(
        registry, "check_ingredient_compatibility", {"ingredients": ["Retinol", "Glycolic Acid"]}
    )
    assert result.success is True
    expected = check_ingredient_compatibility(["Retinol", "Glycolic Acid"]).model_dump(mode="json")
    assert result.result == expected
    assert len(result.result["interactions"]) == 1
    assert result.result["interactions"][0]["severity"] == "caution"


def test_check_ingredient_compatibility_tool_rejects_empty_list() -> None:
    registry = build_tool_registry()
    result = execute_tool(registry, "check_ingredient_compatibility", {"ingredients": []})
    assert result.success is False


def test_analyze_product_tool_is_stateless_and_matches_compatibility_engine() -> None:
    registry = build_tool_registry()
    result = execute_tool(
        registry,
        "analyze_product",
        {"name": "Retinol Serum", "raw_ingredient_text": "Retinol, Glycolic Acid"},
    )
    assert result.success is True
    expected = check_ingredient_compatibility(["Retinol", "Glycolic Acid"]).model_dump(mode="json")
    assert result.result == expected
    # Stateless: no product_id/session_id field -- nothing was persisted.
    assert "product_id" not in result.result
    assert "session_id" not in result.result


def test_compare_products_tool_matches_comparator_output() -> None:
    registry = build_tool_registry()
    request = ProductCompareRequest(
        product_a=ProductCompareItem(name="A", raw_ingredient_text="Retinol, Niacinamide"),
        product_b=ProductCompareItem(name="B", raw_ingredient_text="Retinol, Salicylic Acid"),
    )
    result = execute_tool(
        registry,
        "compare_products",
        {
            "product_a": {"name": "A", "raw_ingredient_text": "Retinol, Niacinamide"},
            "product_b": {"name": "B", "raw_ingredient_text": "Retinol, Salicylic Acid"},
        },
    )
    assert result.success is True
    assert result.result == compare_products(request).model_dump(mode="json")
    assert result.result["shared_ingredients"] == ["retinol"]


def test_analyze_routine_tool_matches_analyzer_output() -> None:
    registry = build_tool_registry()
    request = RoutineAnalysisRequest(
        products=[
            RoutineProductInput(product_name="A", raw_ingredients="Retinol"),
            RoutineProductInput(product_name="B", raw_ingredients="Glycolic Acid"),
        ]
    )
    result = execute_tool(
        registry,
        "analyze_routine",
        {
            "products": [
                {"product_name": "A", "raw_ingredients": "Retinol"},
                {"product_name": "B", "raw_ingredients": "Glycolic Acid"},
            ]
        },
    )
    assert result.success is True
    assert result.result == analyze_routine(request).model_dump(mode="json")
    assert len(result.result["interactions"]) == 1


def test_get_ingredient_information_tool_matches_normalizer_output() -> None:
    registry = build_tool_registry()
    result = execute_tool(registry, "get_ingredient_information", {"ingredient": "Retinol"})
    assert result.success is True
    expected = normalize_ingredient("Retinol", get_rule_set()).model_dump(mode="json")
    assert result.result == expected
    assert result.result["matched"] is True
    assert result.result["normalized_name"] == "retinol"
    assert "retinoid" in result.result["categories"]


def test_get_ingredient_information_tool_unknown_ingredient_is_honest() -> None:
    registry = build_tool_registry()
    result = execute_tool(registry, "get_ingredient_information", {"ingredient": "Definitely Not A Real Thing"})
    assert result.success is True
    assert result.result["matched"] is False
    assert result.result["normalized_name"] is None


def test_tools_never_invent_an_interaction_for_unknown_ingredients() -> None:
    registry = build_tool_registry()
    result = execute_tool(
        registry, "check_ingredient_compatibility", {"ingredients": ["Not Real One", "Not Real Two"]}
    )
    assert result.success is True
    assert result.result["interactions"] == []
    assert set(result.result["unknown_ingredients"]) == {"Not Real One", "Not Real Two"}
