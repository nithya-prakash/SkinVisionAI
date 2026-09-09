"""Tests for app.agent.validation: anti-hallucination checks against the
accumulated tool trace. Mirrors tests/llm/test_validation.py's structure,
extended to a multi-tool-call trace instead of a single deterministic
result.
"""
from __future__ import annotations

import pytest

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.agent.trace import ToolCallTraceEntry
from app.agent.validation import HallucinationError, build_ground_truth, validate_agent_answer
from app.llm.validation import DIAGNOSTIC_CLAIM_PATTERN, normalize_for_validation

_GROUNDED_TRACE = [
    ToolCallTraceEntry(
        tool_name="check_ingredient_compatibility",
        arguments={"ingredients": ["retinol", "glycolic acid"]},
        result={
            "interactions": [
                {
                    "rule_id": "retinol_glycolic_acid_caution",
                    "ingredient_a": "retinol",
                    "ingredient_b": "glycolic_acid",
                    "severity": "caution",
                    "message": "...",
                    "source": "Cleveland Clinic",
                    "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol",
                }
            ],
            "ingredients": [
                {"raw_text": "retinol", "normalized_name": "retinol", "matched": True, "categories": []},
                {
                    "raw_text": "glycolic acid",
                    "normalized_name": "glycolic_acid",
                    "matched": True,
                    "categories": [],
                },
            ],
        },
        call_index=0,
        success=True,
    )
]


def _answer(**overrides) -> AgentFinalAnswerLLMOutput:
    data = {"answer": "This is a caution-level interaction.", "key_points": [], "limitations": []}
    data.update(overrides)
    return AgentFinalAnswerLLMOutput(**data)


# --- build_ground_truth ---


def test_ground_truth_collects_facts_from_successful_calls() -> None:
    gt = build_ground_truth(_GROUNDED_TRACE)
    assert "retinol_glycolic_acid_caution" in gt.known_rule_ids
    assert "retinol" in gt.known_ingredient_names
    assert "glycolic_acid" in gt.known_ingredient_names
    assert "Cleveland Clinic" in gt.known_source_names


def test_ground_truth_ignores_failed_calls() -> None:
    trace = [
        ToolCallTraceEntry(
            tool_name="check_ingredient_compatibility",
            arguments={},
            result=None,
            call_index=0,
            success=False,
            error="invalid arguments",
        )
    ]
    gt = build_ground_truth(trace)
    assert gt.known_rule_ids == frozenset()
    assert gt.known_ingredient_names == frozenset()


def test_ground_truth_from_empty_trace_is_empty() -> None:
    gt = build_ground_truth([])
    assert gt.known_ingredient_names == frozenset()
    assert gt.known_source_names == frozenset()


# --- Positive controls ---


def test_grounded_answer_passes() -> None:
    validate_agent_answer(_answer(answer="Retinol and glycolic acid have a documented caution-level interaction."), _GROUNDED_TRACE)


def test_answer_citing_real_source_passes() -> None:
    validate_agent_answer(
        _answer(answer="According to Cleveland Clinic, this combination may cause irritation."),
        _GROUNDED_TRACE,
    )


# --- The 5 required adversarial scenarios (spec section 27) ---


def test_invented_ingredient_rejected() -> None:
    # "hyaluronic acid" is a real canonical ingredient in this system's
    # rule set, but never appeared in _GROUNDED_TRACE -- mentioning it
    # must be rejected as ungrounded, exactly like a wholly-invented name
    # would be (the check works the same way for both).
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(answer="You should also consider adding hyaluronic acid to this routine."),
            _GROUNDED_TRACE,
        )
    assert exc_info.value.code == "unknown_ingredient"


def test_unsafe_claim_contradicting_caution_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(answer="Retinol and glycolic acid are completely safe together."), _GROUNDED_TRACE
        )
    assert exc_info.value.code == "overclaim"


def test_fabricated_citation_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(answer="According to a 2026 AAD study, this is a caution-level pairing."),
            _GROUNDED_TRACE,
        )
    assert exc_info.value.code == "fabricated_citation"


def test_citation_with_zero_tool_calls_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(_answer(answer="Source: general dermatology knowledge."), [])
    assert exc_info.value.code == "fabricated_citation"


def test_unknown_tool_request_is_rejected_at_the_registry_not_here() -> None:
    # Rejecting an unregistered tool name (e.g. "execute_python", "import")
    # happens in app.agent.registry.execute_tool, before any trace entry
    # or final answer exists -- see tests/agent/test_registry.py. This
    # test documents that boundary rather than duplicating it.
    from app.agent.registry import ToolRegistry, execute_tool

    result = execute_tool(ToolRegistry(), "execute_python", {"code": "..."})
    assert result.success is False
    assert "unknown tool" in result.error


def test_answer_without_required_tool_call_rejected() -> None:
    # No tool was called at all (empty trace) but the answer makes a
    # specific ingredient-grounded claim -- must be rejected, since
    # nothing established these ingredients exist in this analysis.
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(answer="Retinol and niacinamide work well in the same routine."), []
        )
    assert exc_info.value.code == "unknown_ingredient"


# --- Additional coverage: fabricated numeric claim ---


def test_fabricated_numeric_claim_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(_answer(answer="This combination is rated 8 out of 10 for safety."), _GROUNDED_TRACE)
    assert exc_info.value.code == "fabricated_number"


# --- Determinism ---


def test_validation_is_deterministic() -> None:
    answer = _answer(answer="Retinol and glycolic acid have a documented caution-level interaction.")
    validate_agent_answer(answer, _GROUNDED_TRACE)
    validate_agent_answer(answer, _GROUNDED_TRACE)  # no exception either time -- no hidden state


# --- Diagnostic-claim detection (Phase 10) ---------------------------------
#
# Reuses the exact same DIAGNOSTIC_CLAIM_PATTERN/normalize_for_validation
# from app.llm.validation (see tests/llm/test_validation.py for the full
# positive/negative case matrix) -- these tests confirm the agent path
# wires them in correctly, not that the pattern itself is correct again.


@pytest.mark.parametrize(
    "phrase",
    [
        "You have acne.",
        "this is rosacea",
        "You have a confirmed skin disease.",
        "This requires medical treatment.",
        "A diagnosis based on this photo suggests treatment is needed.",
    ],
)
def test_diagnostic_claim_rejected(phrase: str) -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(_answer(answer=phrase), _GROUNDED_TRACE)
    assert exc_info.value.code == "diagnostic_claim"


def test_diagnostic_claim_embedded_in_grounded_answer_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(
                answer=(
                    "Retinol and glycolic acid have a documented caution-level "
                    "interaction. Also, you have acne."
                )
            ),
            _GROUNDED_TRACE,
        )
    assert exc_info.value.code == "diagnostic_claim"


def test_diagnostic_claim_in_limitations_rejected() -> None:
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(
            _answer(
                answer="Retinol and glycolic acid have a documented caution-level interaction.",
                limitations=["This does not replace the fact that you have rosacea."],
            ),
            _GROUNDED_TRACE,
        )
    assert exc_info.value.code == "diagnostic_claim"


@pytest.mark.parametrize(
    "phrase",
    [
        "If you have persistent acne, consult a dermatologist.",
        "You don't have rosacea.",
        "This is not a medical diagnosis.",
        "Retinol is commonly used in acne treatment products.",
    ],
)
def test_legitimate_educational_wording_not_rejected(phrase: str) -> None:
    validate_agent_answer(_answer(answer=phrase), _GROUNDED_TRACE)  # must not raise


def test_zero_width_space_does_not_bypass_diagnostic_check_in_agent_path() -> None:
    evasive = "you\u200b have\u200b acne"  # zero width space
    assert DIAGNOSTIC_CLAIM_PATTERN.search(evasive) is None  # unnormalized: dodges the pattern
    with pytest.raises(HallucinationError) as exc_info:
        validate_agent_answer(_answer(answer=evasive), _GROUNDED_TRACE)
    assert exc_info.value.code == "diagnostic_claim"


def test_normalize_for_validation_is_the_same_function_reused_from_llm_validation() -> None:
    # Not re-testing normalization itself (see tests/llm/test_validation.py)
    # -- just confirming app.agent.validation imports and reuses the one
    # shared implementation rather than a drifted second copy.
    from app.agent import validation as agent_validation

    assert agent_validation.normalize_for_validation is normalize_for_validation
