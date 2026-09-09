"""The public API contract for LLM-generated explanations (Phase 6).

``Explanation`` is deliberately assembled by the backend, never returned
from the LLM directly: ``severity``, ``source``, and ``source_url`` on
every item come from the trusted deterministic result
(``app.llm.context``), not from ``app.llm.schemas.ExplanationLLMOutput`` --
that raw model has no such fields at all, so the LLM has no field to
write an altered severity or a fabricated citation into. Only the
``explanation`` narrative text on each item, and the top-level
``summary``/``key_points``/``routine_notes``, come from the model, and
only after passing ``app.llm.validation``.

An ``ExplanationEnvelope`` always accompanies its deterministic analysis
result -- the analysis is never withheld because the LLM failed; see
``app.services.explanation_service``.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import DISCLAIMER
from app.schemas.ingredient import CompatibilityResult, RuleSeverity
from app.schemas.product import ProductComparisonResult
from app.schemas.routine import RoutineAnalysisResult


class ExplanationStatus(StrEnum):
    """Whether an AI explanation is present for this response."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class InteractionExplanation(BaseModel):
    """One deterministic interaction plus its AI-generated narrative.

    Every field except ``explanation`` is copied verbatim from the
    deterministic result -- the LLM never supplies or alters them.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str | None
    ingredient_a: str
    ingredient_b: str
    severity: RuleSeverity
    message: str
    source: str | None
    source_url: str | None
    explanation: str


class OverlapExplanation(BaseModel):
    """One deterministic overlapping-active finding plus its AI narrative."""

    model_config = ConfigDict(extra="forbid")

    ingredient: str
    products: list[str]
    message: str
    source: str | None
    source_url: str | None
    explanation: str


class Explanation(BaseModel):
    """The full AI explanation for one analysis result."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_points: list[str] = Field(default_factory=list)
    interactions_explained: list[InteractionExplanation] = Field(default_factory=list)
    overlap_explained: list[OverlapExplanation] = Field(default_factory=list)
    routine_notes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class _ExplanationEnvelopeBase(BaseModel):
    """Shared shape: the trusted deterministic analysis is always present;
    the AI explanation is present only when generation succeeded. The
    deterministic result is never withheld because the LLM failed.
    """

    model_config = ConfigDict(extra="forbid")

    explanation: Explanation | None
    explanation_status: ExplanationStatus
    explanation_error: str | None = Field(
        default=None,
        description="User-safe reason the explanation is unavailable. Never the raw provider error.",
    )


class ProductExplanationResponse(_ExplanationEnvelopeBase):
    """Response for ``POST /api/explanations/product``."""

    analysis: CompatibilityResult


class ComparisonExplanationResponse(_ExplanationEnvelopeBase):
    """Response for ``POST /api/explanations/compare``."""

    analysis: ProductComparisonResult


class RoutineExplanationResponse(_ExplanationEnvelopeBase):
    """Response for ``POST /api/explanations/routine``."""

    analysis: RoutineAnalysisResult
