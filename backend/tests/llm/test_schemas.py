"""Tests for app.llm.schemas -- the raw LLM structured-output contract.

Confirms, at the schema level, that there is simply no field for the LLM
to write a severity, source, or citation into -- the strongest possible
guarantee against those being altered.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.llm.schemas import ExplanationLLMOutput, InteractionExplanationItem, OverlapExplanationItem


def test_valid_minimal_output() -> None:
    output = ExplanationLLMOutput(summary="A short summary.")
    assert output.key_points == []
    assert output.interactions_explained == []


def test_valid_full_output() -> None:
    output = ExplanationLLMOutput(
        summary="Summary.",
        key_points=["Point one.", "Point two."],
        interactions_explained=[
            InteractionExplanationItem(rule_id="retinol_glycolic_acid_caution", explanation="...")
        ],
        overlap_explained=[OverlapExplanationItem(ingredient="retinol", explanation="...")],
        routine_notes=["A note."],
    )
    assert len(output.interactions_explained) == 1


def test_rejects_empty_summary() -> None:
    with pytest.raises(ValidationError):
        ExplanationLLMOutput(summary="")


def test_rejects_missing_summary() -> None:
    with pytest.raises(ValidationError):
        ExplanationLLMOutput()


@pytest.mark.parametrize(
    "banned_field",
    ["severity", "source", "source_url", "citation", "score", "confidence"],
)
def test_output_schema_has_no_severity_or_citation_fields(banned_field: str) -> None:
    """The raw LLM output schema must never have grown a field the model
    could use to assert/alter a severity or citation -- this is the
    structural guarantee described in docs/llm.md.
    """
    schema_fields = set(ExplanationLLMOutput.model_fields)
    schema_fields |= set(InteractionExplanationItem.model_fields)
    schema_fields |= set(OverlapExplanationItem.model_fields)
    assert banned_field not in schema_fields


def test_top_level_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ExplanationLLMOutput(summary="x", skin_health_score=95)


def test_interaction_item_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        InteractionExplanationItem(rule_id="x", explanation="y", severity="incompatibility")


def test_overlap_item_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OverlapExplanationItem(ingredient="x", explanation="y", source="Fabricated Source")


def test_interaction_item_requires_rule_id() -> None:
    with pytest.raises(ValidationError):
        InteractionExplanationItem(explanation="y")


def test_key_points_max_length_enforced() -> None:
    with pytest.raises(ValidationError):
        ExplanationLLMOutput(summary="x", key_points=[f"point {i}" for i in range(20)])
