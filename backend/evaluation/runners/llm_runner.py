"""Runs the LLM explanation-layer evaluation dataset against the real
Phase 6 pipeline (app.services.explanation_service.explain_product,
which calls the real app.llm.validation.validate_explanation) -- never a
second, parallel validator. Fully offline: FakeLLMProvider only, no
network, no API key.
"""
from __future__ import annotations

from app.llm.provider import FakeLLMProvider
from app.schemas.product import ProductAnalyzeRequest
from app.services.explanation_service import explain_product
from evaluation.datasets.llm import LLM_EXPLANATION_CASES, PRODUCT_NAME, RAW_INGREDIENT_TEXT
from evaluation.runners.base import EvalResult, require_non_empty, require_unique_case_ids

SUBSYSTEM = "llm"


async def _run_cases() -> list[EvalResult]:
    require_non_empty(list(LLM_EXPLANATION_CASES), "llm.LLM_EXPLANATION_CASES")
    require_unique_case_ids([c.case_id for c in LLM_EXPLANATION_CASES], "llm.LLM_EXPLANATION_CASES")

    request = ProductAnalyzeRequest(name=PRODUCT_NAME, raw_ingredient_text=RAW_INGREDIENT_TEXT)
    results: list[EvalResult] = []

    for case in LLM_EXPLANATION_CASES:
        provider = FakeLLMProvider(fixed_response=case.fixed_response, raise_error=case.raise_error)
        response = await explain_product(request, provider)
        actual_status = response.explanation_status.value

        failures = []
        if actual_status != case.expect_status:
            failures.append(f"expected explanation_status={case.expect_status!r}, got {actual_status!r}")

        # The deterministic analysis must always be present and complete,
        # regardless of whether the explanation was accepted -- a
        # rejected/unavailable explanation must never withhold it.
        if response.analysis is None:
            failures.append("the deterministic analysis was withheld -- must never happen")

        # A rejected/unavailable case's error message (if any) must never
        # contain raw exception text -- checked directly here rather than
        # trusted, since this is exactly the kind of leak Phase 10's
        # safety audit exists to catch.
        if case.raise_error is not None:
            raw_text = str(case.raise_error)
            if response.explanation_error and raw_text in response.explanation_error:
                failures.append(f"raw exception text leaked into explanation_error: {raw_text!r}")

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                expected={"status": case.expect_status, "rejection_code": case.expect_rejection_code},
                actual={"status": actual_status, "error": response.explanation_error},
            )
        )
    return results


async def run() -> list[EvalResult]:
    return await _run_cases()
