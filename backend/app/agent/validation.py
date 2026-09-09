"""Anti-hallucination validation for the agent's final answer.

Reuses Phase 6's heuristic textual checks (overclaiming, fabricated
numbers, fabricated citations, unknown-ingredient mentions, diagnostic
claims, Unicode normalization -- Phase 10 added the last two) verbatim
-- see ``app.llm.validation`` -- against a ground-truth set built from
the *accumulated tool trace* instead of a single deterministic result,
since one agent turn may call more than one tool. Same
``HallucinationError`` type, same deliberate bias toward over-rejection:
a false positive degrades to ``AgentStatus.VALIDATION_ERROR`` with the
tool trace itself still returned (it was never unsafe, only the
free-text summary of it); a false negative is the actual failure this
module exists to prevent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.agent.trace import ToolCallTraceEntry
from app.llm.validation import (
    CITATION_LEAD_IN_PATTERN,
    DIAGNOSTIC_CLAIM_PATTERN,
    NUMERIC_CLAIM_PATTERN,
    OVERCLAIM_PATTERNS,
    URL_PATTERN,
    HallucinationError,
    mentioned_known_ingredients,
    normalize_for_validation,
)

_FACT_KEYS = (
    "rule_id",
    "ingredient_a",
    "ingredient_b",
    "ingredient",
    "normalized_name",
    "source",
    "source_url",
)


@dataclass(frozen=True)
class AgentGroundTruth:
    """Everything the agent's final answer is allowed to reference,
    derived from every *successful* tool call's result so far this turn.
    """

    known_rule_ids: frozenset[str] = frozenset()
    known_ingredient_names: frozenset[str] = frozenset()
    known_source_names: frozenset[str] = frozenset()
    known_source_urls: frozenset[str] = frozenset()


def _collect(obj: Any, buckets: dict[str, set[str]]) -> None:
    if isinstance(obj, dict):
        for key in _FACT_KEYS:
            value = obj.get(key)
            if isinstance(value, str) and value:
                buckets[key].add(value)
        for value in obj.values():
            _collect(value, buckets)
    elif isinstance(obj, list):
        for item in obj:
            _collect(item, buckets)


def build_ground_truth(trace: list[ToolCallTraceEntry]) -> AgentGroundTruth:
    """Walk every successful tool call's result and collect the facts the
    final answer is allowed to reference. A failed tool call contributes
    nothing (its ``result`` is ``None``) -- the agent must not treat a
    failed lookup as having established anything. An empty trace (the
    model answered without calling any tool) produces an empty ground
    truth, which is exactly what makes an ungrounded compatibility claim
    fail the checks below.
    """
    buckets: dict[str, set[str]] = {key: set() for key in _FACT_KEYS}
    for entry in trace:
        if entry.success and entry.result is not None:
            _collect(entry.result, buckets)

    ingredient_names = (
        buckets["ingredient_a"]
        | buckets["ingredient_b"]
        | buckets["ingredient"]
        | buckets["normalized_name"]
    )
    return AgentGroundTruth(
        known_rule_ids=frozenset(buckets["rule_id"]),
        known_ingredient_names=frozenset(ingredient_names),
        known_source_names=frozenset(buckets["source"]),
        known_source_urls=frozenset(buckets["source_url"]),
    )


def _final_answer_text(output: AgentFinalAnswerLLMOutput) -> str:
    return " ".join([output.answer, *output.key_points, *output.limitations])


def validate_agent_answer(output: AgentFinalAnswerLLMOutput, trace: list[ToolCallTraceEntry]) -> None:
    """Raise ``HallucinationError`` if the agent's final answer asserts
    anything not grounded in the accumulated tool trace. Returns normally
    if the answer is safe to return to the user.
    """
    ground_truth = build_ground_truth(trace)
    combined_text = normalize_for_validation(_final_answer_text(output))
    lowered = combined_text.lower()

    for phrase in OVERCLAIM_PATTERNS:
        if phrase in lowered:
            raise HallucinationError("overclaim", f"contains an overclaiming safety phrase: {phrase!r}")

    diagnostic_match = DIAGNOSTIC_CLAIM_PATTERN.search(combined_text)
    if diagnostic_match:
        raise HallucinationError(
            "diagnostic_claim",
            "contains language that asserts or implies a medical diagnosis: "
            f"{diagnostic_match.group(0)!r}",
        )

    if NUMERIC_CLAIM_PATTERN.search(combined_text):
        raise HallucinationError(
            "fabricated_number", "contains a numeric/percentage claim not present in any tool result"
        )

    for url in URL_PATTERN.findall(combined_text):
        if url.rstrip(".,)") not in ground_truth.known_source_urls:
            raise HallucinationError(
                "fabricated_citation", f"references a URL not present in any tool result: {url}"
            )

    if CITATION_LEAD_IN_PATTERN.search(combined_text):
        if not ground_truth.known_source_names:
            # Stricter than Phase 6 here: Phase 6 always has exactly one
            # deterministic result to check against, so "zero known
            # sources" never comes up in practice. The agent can
            # legitimately answer with zero successful tool calls (e.g.
            # a non-domain question), so a citation phrase with nothing
            # in the trace to back it is unambiguously fabricated.
            raise HallucinationError(
                "fabricated_citation", "references a source/citation but no tool call produced one"
            )
        if not any(name.lower() in lowered for name in ground_truth.known_source_names):
            raise HallucinationError(
                "fabricated_citation", "references a source/citation not present in any tool result"
            )

    mentioned = mentioned_known_ingredients(combined_text)
    unknown_mentions = mentioned - ground_truth.known_ingredient_names
    if unknown_mentions:
        raise HallucinationError(
            "unknown_ingredient",
            f"mentions ingredient(s) not present in any tool result: {sorted(unknown_mentions)}",
        )
