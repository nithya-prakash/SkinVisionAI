"""Explanation orchestration (Phase 6; Phase 8 adds opt-in persistence).

API route -> explanation_service -> (re-runs the Phase 4/5 deterministic
engine itself, never trusts a client-submitted "already computed" result)
-> LLM provider -> anti-hallucination validation -> merge with trusted
deterministic fields -> Explanation. The deterministic analysis is always
returned, even when the explanation fails -- see ``_generate_explanation``.

Stateless by default (matches Phase 5's routine/compare endpoints). Phase
8's opt-in ``persist=True`` on ``ProductCompareRequest``/
``RoutineAnalysisRequest`` (reused verbatim here -- the explanation
endpoints take the exact same request schemas as their deterministic-only
siblings) also persists when set here, so the frontend's "AI Explanation"
flows (which call these endpoints, not the deterministic-only ones) get a
retrievable id too. No LLM call is ever made from anywhere except this
module.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingredients.compatibility import check_ingredient_compatibility
from app.ingredients.parser import parse_ingredient_list
from app.llm.base import LLMProvider, LLMProviderError
from app.llm.context import (
    DeterministicContext,
    build_comparison_context,
    build_product_context,
    build_routine_context,
)
from app.llm.prompts import SYSTEM_PROMPT
from app.llm.schemas import ExplanationLLMOutput
from app.llm.validation import HallucinationError, validate_explanation
from app.products.comparator import compare_products
from app.routine.analyzer import analyze_routine
from app.schemas.explanation import (
    ComparisonExplanationResponse,
    Explanation,
    ExplanationStatus,
    InteractionExplanation,
    OverlapExplanation,
    ProductExplanationResponse,
    RoutineExplanationResponse,
)
from app.schemas.ingredient import CompatibilityResult
from app.schemas.product import ProductAnalyzeRequest, ProductCompareRequest, ProductComparisonResult
from app.schemas.routine import RoutineAnalysisRequest, RoutineAnalysisResult
from app.models.session import UserSession
from app.services.persistence_service import persist_comparison, persist_routine_analysis

logger = logging.getLogger(__name__)


def _safe_error_message(exc: Exception) -> str:
    """A short, generic, user-safe message -- never the raw provider
    exception text, which could carry account/request details.
    """
    from app.llm.base import (
        LLMAuthenticationError,
        LLMRateLimitError,
        LLMResponseValidationError,
        LLMTimeoutError,
    )

    if isinstance(exc, LLMAuthenticationError):
        return "AI explanation is currently unavailable (provider authentication issue)."
    if isinstance(exc, LLMRateLimitError):
        return "AI explanation is currently unavailable (rate limited); please try again shortly."
    if isinstance(exc, LLMTimeoutError):
        return "AI explanation is currently unavailable (the request timed out)."
    if isinstance(exc, LLMResponseValidationError):
        return "AI explanation is currently unavailable (the response could not be validated)."
    if isinstance(exc, HallucinationError):
        return "AI explanation is currently unavailable (the generated explanation did not pass validation)."
    return "AI explanation is currently unavailable."


async def _generate_raw_explanation(
    provider: LLMProvider, context: DeterministicContext
) -> tuple[ExplanationLLMOutput | None, str | None]:
    """Call the provider and validate its output. Returns
    ``(output, None)`` on success or ``(None, safe_error_message)`` on any
    failure -- never raises, so a failing explanation never breaks the
    surrounding deterministic-analysis request.
    """
    try:
        raw = await provider.generate_structured(SYSTEM_PROMPT, context.payload, ExplanationLLMOutput)
        validate_explanation(raw, context)
    except LLMProviderError as exc:
        logger.warning("llm_explanation_unavailable error_type=%s", type(exc).__name__)
        return None, _safe_error_message(exc)
    except HallucinationError as exc:
        logger.warning("llm_explanation_rejected code=%s", exc.code)
        return None, _safe_error_message(exc)
    except Exception:  # defensive: an explanation failure must never break the request
        logger.exception("llm_explanation_unexpected_error")
        return None, "AI explanation is currently unavailable."

    return raw, None


def _merge_interactions(
    llm_items, deterministic_interactions
) -> list[InteractionExplanation]:
    by_rule_id = {i.rule_id: i for i in deterministic_interactions if i.rule_id}
    return [
        InteractionExplanation(
            rule_id=det.rule_id,
            ingredient_a=det.ingredient_a,
            ingredient_b=det.ingredient_b,
            severity=det.severity,
            message=det.message,
            source=det.source,
            source_url=det.source_url,
            explanation=item.explanation,
        )
        for item in llm_items
        if (det := by_rule_id.get(item.rule_id)) is not None
    ]


def _merge_overlaps(llm_items, deterministic_overlaps) -> list[OverlapExplanation]:
    by_ingredient = {o.ingredient: o for o in deterministic_overlaps}
    return [
        OverlapExplanation(
            ingredient=det.ingredient,
            products=det.products,
            message=det.message,
            source=det.source,
            source_url=det.source_url,
            explanation=item.explanation,
        )
        for item in llm_items
        if (det := by_ingredient.get(item.ingredient)) is not None
    ]


async def explain_product(
    request: ProductAnalyzeRequest, provider: LLMProvider
) -> ProductExplanationResponse:
    tokens = parse_ingredient_list(request.raw_ingredient_text)
    result: CompatibilityResult = check_ingredient_compatibility(tokens)
    context = build_product_context(result)

    raw, error = await _generate_raw_explanation(provider, context)
    if raw is None:
        return ProductExplanationResponse(
            analysis=result,
            explanation=None,
            explanation_status=ExplanationStatus.UNAVAILABLE,
            explanation_error=error,
        )

    explanation = Explanation(
        summary=raw.summary,
        key_points=raw.key_points,
        interactions_explained=_merge_interactions(raw.interactions_explained, result.interactions),
        overlap_explained=[],
        routine_notes=[],
        limitations=result.limitations,
    )
    return ProductExplanationResponse(
        analysis=result, explanation=explanation, explanation_status=ExplanationStatus.AVAILABLE
    )


async def explain_comparison(
    request: ProductCompareRequest,
    provider: LLMProvider,
    db: AsyncSession | None = None,
    session: UserSession | None = None,
) -> ComparisonExplanationResponse:
    result: ProductComparisonResult = compare_products(request)
    if request.persist:
        assert db is not None and session is not None, (
            "db and session are required when request.persist is True"
        )
        record = await persist_comparison(db, session, request, result)
        result = result.model_copy(update={"id": record.id})
    context = build_comparison_context(result)

    raw, error = await _generate_raw_explanation(provider, context)
    if raw is None:
        return ComparisonExplanationResponse(
            analysis=result,
            explanation=None,
            explanation_status=ExplanationStatus.UNAVAILABLE,
            explanation_error=error,
        )

    explanation = Explanation(
        summary=raw.summary,
        key_points=raw.key_points,
        interactions_explained=_merge_interactions(raw.interactions_explained, result.interactions),
        overlap_explained=[],
        routine_notes=[],
        limitations=result.limitations,
    )
    return ComparisonExplanationResponse(
        analysis=result, explanation=explanation, explanation_status=ExplanationStatus.AVAILABLE
    )


async def explain_routine(
    request: RoutineAnalysisRequest,
    provider: LLMProvider,
    db: AsyncSession | None = None,
    session: UserSession | None = None,
) -> RoutineExplanationResponse:
    result: RoutineAnalysisResult = analyze_routine(request)
    if request.persist:
        assert db is not None and session is not None, (
            "db and session are required when request.persist is True"
        )
        record = await persist_routine_analysis(db, session, request, result)
        result = result.model_copy(update={"id": record.id})
    context = build_routine_context(result)

    raw, error = await _generate_raw_explanation(provider, context)
    if raw is None:
        return RoutineExplanationResponse(
            analysis=result,
            explanation=None,
            explanation_status=ExplanationStatus.UNAVAILABLE,
            explanation_error=error,
        )

    explanation = Explanation(
        summary=raw.summary,
        key_points=raw.key_points,
        interactions_explained=_merge_interactions(raw.interactions_explained, result.interactions),
        overlap_explained=_merge_overlaps(raw.overlap_explained, result.overlapping_actives),
        routine_notes=raw.routine_notes,
        limitations=result.limitations,
    )
    return RoutineExplanationResponse(
        analysis=result, explanation=explanation, explanation_status=ExplanationStatus.AVAILABLE
    )
