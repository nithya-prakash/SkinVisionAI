"""Runs the ingredient evaluation dataset against the real Phase 4
deterministic engine (app.ingredients.parser/normalizer/compatibility),
using the real production rule set (app.ingredients.rules.get_rule_set())
-- never a second, parallel implementation.
"""
from __future__ import annotations

from app.ingredients.compatibility import check_pair
from app.ingredients.normalizer import normalize_ingredient
from app.ingredients.parser import parse_ingredient_list
from app.ingredients.rules import get_rule_set
from evaluation.datasets.ingredients import (
    COMPATIBILITY_CASES,
    NORMALIZATION_CASES,
    PARSE_LIST_CASES,
)
from evaluation.metrics import assert_deterministic
from evaluation.runners.base import EvalResult, require_non_empty, require_unique_case_ids

SUBSYSTEM = "ingredients"
RULE_SET = get_rule_set()


def _run_normalization_cases() -> list[EvalResult]:
    require_non_empty(list(NORMALIZATION_CASES), "ingredients.NORMALIZATION_CASES")
    require_unique_case_ids([c.case_id for c in NORMALIZATION_CASES], "ingredients.NORMALIZATION_CASES")

    results: list[EvalResult] = []
    for case in NORMALIZATION_CASES:
        normalized = normalize_ingredient(case.raw_text, RULE_SET)
        failures = []
        if normalized.matched != case.expect_matched:
            failures.append(f"expected matched={case.expect_matched}, got {normalized.matched}")
        if case.expect_canonical is not None and normalized.normalized_name != case.expect_canonical:
            failures.append(
                f"expected canonical={case.expect_canonical!r}, got {normalized.normalized_name!r}"
            )
        if normalized.ambiguous != case.expect_ambiguous:
            failures.append(f"expected ambiguous={case.expect_ambiguous}, got {normalized.ambiguous}")
        if case.expect_candidates and set(normalized.candidates) != set(case.expect_candidates):
            failures.append(
                f"expected candidates={sorted(case.expect_candidates)}, got {sorted(normalized.candidates)}"
            )

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                expected={
                    "matched": case.expect_matched,
                    "canonical": case.expect_canonical,
                    "ambiguous": case.expect_ambiguous,
                },
                actual={
                    "matched": normalized.matched,
                    "canonical": normalized.normalized_name,
                    "ambiguous": normalized.ambiguous,
                },
            )
        )
    return results


def _run_parse_list_cases() -> list[EvalResult]:
    require_non_empty(list(PARSE_LIST_CASES), "ingredients.PARSE_LIST_CASES")
    require_unique_case_ids([c.case_id for c in PARSE_LIST_CASES], "ingredients.PARSE_LIST_CASES")

    results: list[EvalResult] = []
    for case in PARSE_LIST_CASES:
        tokens = tuple(parse_ingredient_list(case.raw_text))
        passed = tokens == case.expect_tokens
        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=passed,
                message="" if passed else f"expected {case.expect_tokens}, got {tokens}",
                expected=list(case.expect_tokens),
                actual=list(tokens),
            )
        )
    return results


def _run_compatibility_cases() -> list[EvalResult]:
    require_non_empty(list(COMPATIBILITY_CASES), "ingredients.COMPATIBILITY_CASES")
    require_unique_case_ids([c.case_id for c in COMPATIBILITY_CASES], "ingredients.COMPATIBILITY_CASES")

    results: list[EvalResult] = []
    for case in COMPATIBILITY_CASES:
        interaction = check_pair(case.ingredient_a, case.ingredient_b, RULE_SET)
        failures = []
        if interaction.rule_id != case.expect_rule_id:
            failures.append(f"expected rule_id={case.expect_rule_id!r}, got {interaction.rule_id!r}")
        if case.expect_severity is not None and interaction.severity.value != case.expect_severity:
            failures.append(f"expected severity={case.expect_severity!r}, got {interaction.severity.value!r}")

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                expected={"rule_id": case.expect_rule_id, "severity": case.expect_severity},
                actual={"rule_id": interaction.rule_id, "severity": interaction.severity.value},
            )
        )
    return results


def _run_determinism_case() -> EvalResult:
    def compute() -> tuple:
        interaction = check_pair("retinol", "glycolic_acid", RULE_SET)
        return (interaction.rule_id, interaction.severity.value)

    ok, message = assert_deterministic(compute, repeats=3)
    return EvalResult(
        SUBSYSTEM,
        "compatibility_check_is_deterministic",
        "The same ingredient pair checked 3 times produces an identical result",
        passed=ok,
        message=message,
    )


def run() -> list[EvalResult]:
    results: list[EvalResult] = []
    results.extend(_run_normalization_cases())
    results.extend(_run_parse_list_cases())
    results.extend(_run_compatibility_cases())
    results.append(_run_determinism_case())
    return results
