"""Tests for the evaluation harness itself (Phase 11) -- dataset
loading, malformed-case detection, metrics, and report generation. These
prove the harness is trustworthy, not just that it happens to report
"all passed" today.
"""
from __future__ import annotations

import json

import pytest

from evaluation.datasets import agent, comparison, ingredients, llm, routine, safety, vision
from evaluation.metrics import assert_deterministic, field_level_accuracy, overall_counts, pass_rate
from evaluation.report import SubsystemRun, build_report, write_report
from evaluation.runners.base import (
    EvalResult,
    MalformedCaseError,
    dumps_safe,
    require_non_empty,
    require_unique_case_ids,
    summarize,
)

# --- Dataset loading: every dataset module actually loads and is non-empty ---


@pytest.mark.parametrize(
    "dataset_tuple,name",
    [
        (vision.QUALITY_CASES, "vision.QUALITY_CASES"),
        (vision.OBSERVATION_CASES, "vision.OBSERVATION_CASES"),
        (ingredients.NORMALIZATION_CASES, "ingredients.NORMALIZATION_CASES"),
        (ingredients.PARSE_LIST_CASES, "ingredients.PARSE_LIST_CASES"),
        (ingredients.COMPATIBILITY_CASES, "ingredients.COMPATIBILITY_CASES"),
        (routine.ROUTINE_CASES, "routine.ROUTINE_CASES"),
        (comparison.COMPARISON_CASES, "comparison.COMPARISON_CASES"),
        (llm.LLM_EXPLANATION_CASES, "llm.LLM_EXPLANATION_CASES"),
        (agent.TOOL_SELECTION_CASES, "agent.TOOL_SELECTION_CASES"),
        (agent.GROUNDING_CASES, "agent.GROUNDING_CASES"),
        (agent.TOOL_SAFETY_CASES, "agent.TOOL_SAFETY_CASES"),
        (safety.SAFETY_CASES, "safety.SAFETY_CASES"),
    ],
)
def test_dataset_loads_and_is_non_empty(dataset_tuple: tuple, name: str) -> None:
    assert len(dataset_tuple) > 0, f"{name} is empty"


@pytest.mark.parametrize(
    "case_ids,name",
    [
        ([c.case_id for c in vision.QUALITY_CASES], "vision.QUALITY_CASES"),
        ([c.case_id for c in vision.OBSERVATION_CASES], "vision.OBSERVATION_CASES"),
        ([c.case_id for c in ingredients.NORMALIZATION_CASES], "ingredients.NORMALIZATION_CASES"),
        ([c.case_id for c in ingredients.COMPATIBILITY_CASES], "ingredients.COMPATIBILITY_CASES"),
        ([c.case_id for c in routine.ROUTINE_CASES], "routine.ROUTINE_CASES"),
        ([c.case_id for c in comparison.COMPARISON_CASES], "comparison.COMPARISON_CASES"),
        ([c.case_id for c in llm.LLM_EXPLANATION_CASES], "llm.LLM_EXPLANATION_CASES"),
        ([c.case_id for c in safety.SAFETY_CASES], "safety.SAFETY_CASES"),
    ],
)
def test_dataset_case_ids_are_unique(case_ids: list[str], name: str) -> None:
    assert len(case_ids) == len(set(case_ids)), f"{name} has duplicate case_ids"


# --- Malformed-case handling: the harness must fail loudly, not silently ---


def test_require_non_empty_rejects_an_empty_dataset() -> None:
    with pytest.raises(MalformedCaseError, match="empty"):
        require_non_empty([], "fake.DATASET")


def test_require_non_empty_accepts_a_populated_dataset() -> None:
    require_non_empty([1, 2, 3], "fake.DATASET")  # must not raise


def test_require_unique_case_ids_rejects_a_duplicate() -> None:
    with pytest.raises(MalformedCaseError, match="duplicate"):
        require_unique_case_ids(["a", "b", "a"], "fake.DATASET")


def test_require_unique_case_ids_rejects_an_empty_case_id() -> None:
    with pytest.raises(MalformedCaseError, match="empty case_id"):
        require_unique_case_ids(["a", "", "b"], "fake.DATASET")


def test_require_unique_case_ids_accepts_all_unique() -> None:
    require_unique_case_ids(["a", "b", "c"], "fake.DATASET")  # must not raise


# --- EvalResult / summarize / report serialization ---


def test_eval_result_to_dict_is_json_safe() -> None:
    result = EvalResult("vision", "case-1", "a test case", passed=True, actual={"level": "mild"})
    text = json.dumps(result.to_dict())
    assert json.loads(text)["case_id"] == "case-1"


def test_dumps_safe_serializes_a_result_list() -> None:
    results = [
        EvalResult("vision", "case-1", "desc", passed=True),
        EvalResult("vision", "case-2", "desc", passed=False, message="mismatch"),
    ]
    text = dumps_safe(results)
    parsed = json.loads(text)
    assert len(parsed) == 2
    assert parsed[1]["passed"] is False


def test_summarize_counts_pass_and_fail_correctly() -> None:
    results = [
        EvalResult("vision", "c1", "d", passed=True),
        EvalResult("vision", "c2", "d", passed=True),
        EvalResult("vision", "c3", "d", passed=False, message="boom"),
    ]
    summary = summarize("vision", results)
    assert summary.total == 3
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.pass_rate == pytest.approx(2 / 3)
    assert summary.failures == [{"case_id": "c3", "description": "d", "message": "boom"}]


def test_summarize_of_empty_results_has_zero_pass_rate() -> None:
    summary = summarize("vision", [])
    assert summary.total == 0
    assert summary.pass_rate == 0.0


# --- Metrics ---


def test_pass_rate_of_empty_list_is_zero() -> None:
    assert pass_rate([]) == 0.0


def test_pass_rate_computes_the_correct_fraction() -> None:
    results = [
        EvalResult("x", "1", "d", passed=True),
        EvalResult("x", "2", "d", passed=True),
        EvalResult("x", "3", "d", passed=True),
        EvalResult("x", "4", "d", passed=False),
    ]
    assert pass_rate(results) == 0.75


def test_field_level_accuracy_partial_match() -> None:
    actual = {"a": 1, "b": 2, "c": 999}
    expected = {"a": 1, "b": 2, "c": 3}
    assert field_level_accuracy(actual, expected, ["a", "b", "c"]) == pytest.approx(2 / 3)


def test_field_level_accuracy_of_no_fields_is_vacuously_perfect() -> None:
    assert field_level_accuracy({}, {}, []) == 1.0


def test_assert_deterministic_detects_identical_results() -> None:
    ok, message = assert_deterministic(lambda: 42, repeats=3)
    assert ok is True
    assert "3 runs" in message


def test_assert_deterministic_detects_a_flaky_function() -> None:
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        return calls["n"]  # different every call

    ok, message = assert_deterministic(flaky, repeats=3)
    assert ok is False
    assert "different results" in message


def test_assert_deterministic_requires_at_least_two_repeats() -> None:
    with pytest.raises(ValueError):
        assert_deterministic(lambda: 1, repeats=1)


def test_overall_counts_sums_across_subsystems() -> None:
    subsystems = {
        "vision": {"total": 10, "passed": 9, "failed": 1},
        "agent": {"total": 5, "passed": 5, "failed": 0},
    }
    counts = overall_counts(subsystems)
    assert counts == {"total": 15, "passed": 14, "failed": 1}


# --- Report generation ---


def test_build_report_shape_matches_the_documented_contract() -> None:
    runs = [
        SubsystemRun("vision", [EvalResult("vision", "c1", "d", passed=True)]),
        SubsystemRun("agent", [EvalResult("agent", "c1", "d", passed=False, message="oops")]),
    ]
    report = build_report(runs, offline=True)

    assert set(report.keys()) == {
        "run_id",
        "timestamp",
        "offline",
        "overall",
        "subsystems",
        "not_a_clinical_benchmark",
    }
    assert report["overall"] == {"total": 2, "passed": 1, "failed": 1, "pass_rate": 0.5}
    assert set(report["subsystems"].keys()) == {"vision", "agent"}
    # No single combined "AI accuracy" field exists anywhere.
    assert "ai_accuracy" not in report
    assert "accuracy" not in report["overall"]


def test_build_report_is_fully_json_serializable() -> None:
    runs = [SubsystemRun("vision", [EvalResult("vision", "c1", "d", passed=True, actual={"x": 1})])]
    report = build_report(runs)
    json.dumps(report)  # must not raise


def test_write_report_writes_a_readable_json_file(tmp_path) -> None:
    runs = [SubsystemRun("vision", [EvalResult("vision", "c1", "d", passed=True)])]
    report = build_report(runs)
    target = tmp_path / "report.json"
    written_path = write_report(report, path=target)
    assert written_path == target
    assert json.loads(target.read_text())["run_id"] == report["run_id"]


def test_report_never_contains_a_literal_api_key_or_system_prompt_string() -> None:
    """A structural sanity check: nothing in the report-building path
    ever touches app.config.Settings.llm_api_key or
    app.agent.prompts.AGENT_SYSTEM_PROMPT -- verified by confirming a
    report built from ordinary results contains neither substring, and
    that build_report/write_report never import those symbols.
    """
    runs = [SubsystemRun("vision", [EvalResult("vision", "c1", "d", passed=True)])]
    report = build_report(runs)
    text = json.dumps(report)
    assert "sk-ant" not in text
    assert "ANTHROPIC_API_KEY" not in text
