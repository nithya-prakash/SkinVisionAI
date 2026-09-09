"""Tests for app.llm.prompts -- confirms the system prompt actually states
every non-negotiable rule the master spec requires, rather than just
trusting the docstring/comment. A prompt-wording regression here is a
real, testable regression.
"""
from __future__ import annotations

from app.llm.prompts import SYSTEM_PROMPT


def test_prompt_states_explanation_layer_boundary() -> None:
    assert "explanation layer" in SYSTEM_PROMPT.lower()
    assert "do not determine skincare compatibility" in SYSTEM_PROMPT.lower()
    assert "authoritative" in SYSTEM_PROMPT.lower()


def test_prompt_forbids_inventing_ingredients_and_interactions() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "never invent an ingredient" in lowered
    assert "never invent an interaction" in lowered


def test_prompt_forbids_changing_severity() -> None:
    assert "different severity" in SYSTEM_PROMPT.lower()


def test_prompt_forbids_calculations() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "calculation" in lowered
    assert "percentage" in lowered


def test_prompt_forbids_fabricated_citations() -> None:
    assert "fabricate a source" in SYSTEM_PROMPT.lower()


def test_prompt_forbids_safety_from_absence() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "no known conflict" in lowered
    assert "safe" in lowered


def test_prompt_requires_preserving_limitations_and_uncertainty() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "limitation" in lowered
    assert "uncertainty" in lowered


def test_prompt_forbids_diagnosis_and_prescriptions() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "diagnose" in lowered
    assert "prescription" in lowered
    assert "personalized medical advice" in lowered


def test_prompt_instructs_reference_by_identifier_only() -> None:
    lowered = SYSTEM_PROMPT.lower()
    assert "rule_id" in lowered
    assert "do not restate severity, source, or citation" in lowered
