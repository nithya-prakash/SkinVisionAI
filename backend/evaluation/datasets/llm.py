"""LLM explanation-layer evaluation fixtures (Phase 11).

Every case drives the real Phase 6 pipeline (app.services.explanation_service
-> app.llm.validation.validate_explanation) via a scripted ``FakeLLMProvider``
-- never a second, parallel validation implementation. Ground truth for
"should this be accepted or rejected" is the *actual validator's contract*
(see docs/llm.md), not a guess at what it should do.

Uses ``check_ingredient_compatibility`` over "Retinol, Glycolic Acid" as
the fixed deterministic input for every case, so ``retinol``,
``glycolic_acid``, ``retinol_glycolic_acid_caution`` (severity: caution,
source: Cleveland Clinic) are the only facts genuinely grounded for all
of them -- everything each case's ``fixed_response`` asserts beyond that
is deliberately either grounded (the "valid" case) or not (every
adversarial case).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.llm.base import LLMTimeoutError
from app.llm.schemas import ExplanationLLMOutput, InteractionExplanationItem

PRODUCT_NAME = "Retinol Serum"
RAW_INGREDIENT_TEXT = "Water, Retinol, Glycolic Acid"
GROUNDED_RULE_ID = "retinol_glycolic_acid_caution"


@dataclass(frozen=True)
class LLMExplanationCase:
    case_id: str
    description: str
    fixed_response: ExplanationLLMOutput | None
    raise_error: Exception | None = None
    expect_status: str = "available"  # "available" | "unavailable"
    expect_rejection_code: str | None = None  # HallucinationError.code, when known


def _grounded_interaction_explained(text: str) -> InteractionExplanationItem:
    return InteractionExplanationItem(rule_id=GROUNDED_RULE_ID, explanation=text)


LLM_EXPLANATION_CASES: tuple[LLMExplanationCase, ...] = (
    LLMExplanationCase(
        "llm_valid_grounded_explanation",
        "A plain-language explanation that only restates the deterministic finding is accepted",
        fixed_response=ExplanationLLMOutput(
            summary="This product contains retinol and glycolic acid, which have a documented caution.",
            key_points=["One caution-level interaction was found."],
            interactions_explained=[
                _grounded_interaction_explained(
                    "Combining these two active ingredients may increase irritation for some users."
                )
            ],
        ),
        expect_status="available",
    ),
    LLMExplanationCase(
        "llm_unsupported_ingredient_claim_rejected",
        "Mentioning an ingredient never present in this product is rejected",
        fixed_response=ExplanationLLMOutput(
            summary="You might also consider adding salicylic acid to strengthen this routine.",
        ),
        expect_status="unavailable",
        expect_rejection_code="unknown_ingredient",
    ),
    LLMExplanationCase(
        "llm_unsupported_citation_lead_in_rejected",
        "A citation lead-in phrase naming a source never attached to this finding is rejected",
        fixed_response=ExplanationLLMOutput(
            summary="According to a 2026 dermatology journal, this pairing is well studied.",
        ),
        expect_status="unavailable",
        expect_rejection_code="fabricated_citation",
    ),
    LLMExplanationCase(
        "llm_unsupported_url_rejected",
        "A bare URL not present in the deterministic result's known source URLs is rejected",
        fixed_response=ExplanationLLMOutput(
            summary="See https://totally-fake-dermatology-journal.example/study for details.",
        ),
        expect_status="unavailable",
        expect_rejection_code="fabricated_citation",
    ),
    LLMExplanationCase(
        "llm_unsupported_numeric_claim_rejected",
        "An invented percentage/score not present in the deterministic result is rejected",
        fixed_response=ExplanationLLMOutput(
            summary="This combination carries roughly a 30% chance of irritation.",
        ),
        expect_status="unavailable",
        expect_rejection_code="fabricated_number",
    ),
    LLMExplanationCase(
        "llm_diagnostic_claim_rejected",
        "A diagnostic-sounding assertion about the user is rejected (Phase 10 validator)",
        fixed_response=ExplanationLLMOutput(summary="You have acne, so use this combination carefully."),
        expect_status="unavailable",
        expect_rejection_code="diagnostic_claim",
    ),
    LLMExplanationCase(
        "llm_overclaim_safety_language_rejected",
        "An overclaiming safety phrase not warranted by a 'caution' finding is rejected",
        fixed_response=ExplanationLLMOutput(
            summary="Retinol and glycolic acid are completely safe to use together.",
        ),
        expect_status="unavailable",
        expect_rejection_code="overclaim",
    ),
    LLMExplanationCase(
        "llm_empty_explanation_is_accepted",
        "An explanation with only the required summary field, asserting nothing extra, is accepted",
        fixed_response=ExplanationLLMOutput(summary="This product's ingredients were analyzed."),
        expect_status="available",
    ),
    LLMExplanationCase(
        "llm_provider_unavailable_returns_controlled_unavailable_status",
        "A simulated provider timeout degrades to explanation_status=unavailable, never a crash or a fabricated answer",
        fixed_response=None,
        raise_error=LLMTimeoutError("simulated evaluation timeout"),
        expect_status="unavailable",
    ),
)
