"""End-to-end tests for app.services.explanation_service, using the real
deterministic engines (Phase 4/5) with FakeLLMProvider standing in for the
LLM -- fully offline, no database, no network.
"""
from __future__ import annotations

import pytest

from app.llm.base import LLMTimeoutError
from app.llm.provider import FakeLLMProvider
from app.llm.schemas import ExplanationLLMOutput, InteractionExplanationItem, OverlapExplanationItem
from app.schemas.explanation import ExplanationStatus
from app.schemas.product import ProductAnalyzeRequest, ProductCompareItem, ProductCompareRequest
from app.schemas.routine import RoutineAnalysisRequest, RoutineProductInput
from app.services.explanation_service import explain_comparison, explain_product, explain_routine

pytestmark = pytest.mark.asyncio


# --- Happy path: deterministic analysis + real fake-provider explanation ---


async def test_explain_product_happy_path() -> None:
    request = ProductAnalyzeRequest(name="Retinol Serum", raw_ingredient_text="Retinol, Glycolic Acid")
    response = await explain_product(request, FakeLLMProvider())

    assert response.explanation_status == ExplanationStatus.AVAILABLE
    assert response.explanation is not None
    assert len(response.analysis.interactions) == 1
    assert len(response.explanation.interactions_explained) == 1
    merged = response.explanation.interactions_explained[0]
    assert merged.severity == response.analysis.interactions[0].severity
    assert merged.source == response.analysis.interactions[0].source
    assert response.explanation.disclaimer.startswith("SkinVision AI provides educational")


async def test_explain_comparison_happy_path() -> None:
    request = ProductCompareRequest(
        product_a=ProductCompareItem(name="A", raw_ingredient_text="Retinol, Niacinamide"),
        product_b=ProductCompareItem(name="B", raw_ingredient_text="Retinol, Salicylic Acid"),
    )
    response = await explain_comparison(request, FakeLLMProvider())

    assert response.explanation_status == ExplanationStatus.AVAILABLE
    assert response.explanation is not None
    assert len(response.explanation.interactions_explained) == len(response.analysis.interactions)


async def test_explain_routine_happy_path() -> None:
    request = RoutineAnalysisRequest(
        products=[
            RoutineProductInput(product_name="A", raw_ingredients="Retinol"),
            RoutineProductInput(product_name="B", raw_ingredients="Niacinamide"),
        ]
    )
    response = await explain_routine(request, FakeLLMProvider())

    assert response.explanation_status == ExplanationStatus.AVAILABLE
    assert response.explanation is not None
    assert len(response.explanation.interactions_explained) == len(response.analysis.interactions)


# --- Deterministic analysis always present, even when the LLM fails ---


async def test_explain_routine_llm_failure_still_returns_analysis() -> None:
    request = RoutineAnalysisRequest(
        products=[RoutineProductInput(product_name="A", raw_ingredients="Retinol, Glycolic Acid")]
    )
    response = await explain_routine(request, FakeLLMProvider(raise_error=LLMTimeoutError("simulated")))

    assert response.explanation_status == ExplanationStatus.UNAVAILABLE
    assert response.explanation is None
    assert response.explanation_error is not None
    # The deterministic analysis is fully present and correct regardless.
    assert len(response.analysis.interactions) == 1
    assert response.analysis.interactions[0].severity == "caution"


async def test_explain_product_llm_failure_error_message_is_safe() -> None:
    """The error message shown to the caller must never leak raw provider
    exception details (API keys, request internals, etc.).
    """
    request = ProductAnalyzeRequest(name="A", raw_ingredient_text="Water")
    response = await explain_product(
        request, FakeLLMProvider(raise_error=LLMTimeoutError("secret internal detail xyz"))
    )
    assert response.explanation_error is not None
    assert "secret internal detail xyz" not in response.explanation_error


# --- Hallucinating fake provider is rejected end-to-end ---


async def test_explain_routine_rejects_hallucinated_interaction() -> None:
    request = RoutineAnalysisRequest(
        products=[RoutineProductInput(product_name="A", raw_ingredients="Water")]
    )
    hallucinating = FakeLLMProvider(
        fixed_response=ExplanationLLMOutput(
            summary="Analysis complete.",
            interactions_explained=[
                InteractionExplanationItem(rule_id="fabricated_rule_id", explanation="Fake.")
            ],
        )
    )
    response = await explain_routine(request, hallucinating)

    assert response.explanation_status == ExplanationStatus.UNAVAILABLE
    assert response.explanation is None
    # Deterministic analysis is still returned.
    assert response.analysis is not None


async def test_explain_routine_rejects_overclaiming_summary() -> None:
    request = RoutineAnalysisRequest(
        products=[RoutineProductInput(product_name="A", raw_ingredients="Retinol, Glycolic Acid")]
    )
    hallucinating = FakeLLMProvider(
        fixed_response=ExplanationLLMOutput(summary="This routine is completely safe to use.")
    )
    response = await explain_routine(request, hallucinating)

    assert response.explanation_status == ExplanationStatus.UNAVAILABLE
    assert response.explanation is None


async def test_explain_comparison_rejects_unknown_ingredient_mention() -> None:
    request = ProductCompareRequest(
        product_a=ProductCompareItem(name="A", raw_ingredient_text="Water"),
        product_b=ProductCompareItem(name="B", raw_ingredient_text="Glycerin"),
    )
    hallucinating = FakeLLMProvider(
        fixed_response=ExplanationLLMOutput(
            summary="You should also consider adding retinol to this comparison."
        )
    )
    response = await explain_comparison(request, hallucinating)

    assert response.explanation_status == ExplanationStatus.UNAVAILABLE


# --- Determinism ---


async def test_explanation_service_is_deterministic() -> None:
    request = RoutineAnalysisRequest(
        products=[RoutineProductInput(product_name="A", raw_ingredients="Retinol, Glycolic Acid")]
    )
    first = await explain_routine(request, FakeLLMProvider())
    second = await explain_routine(request, FakeLLMProvider())
    assert first.model_dump() == second.model_dump()


# --- No overlap-explained items requested for single-product/comparison ---


async def test_product_explanation_never_carries_overlap_items() -> None:
    request = ProductAnalyzeRequest(name="A", raw_ingredient_text="Retinol")
    response = await explain_product(request, FakeLLMProvider())
    assert response.explanation.overlap_explained == []
