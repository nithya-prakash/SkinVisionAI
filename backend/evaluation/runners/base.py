"""Shared result type every runner produces, plus small comparison
helpers. Deliberately not a generic "case runner" framework -- each
subsystem's dataset/runner pair is shaped for that subsystem (a vision
case needs an image factory, an agent case needs an async script), and
forcing them into one abstract shape would fight the content rather than
simplify it (the same judgment call this project already made for
frontend components in Phase 9 -- see docs/frontend.md).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvalResult:
    """One case's outcome. ``expected``/``actual`` are small, JSON-safe
    values (never a raw object, an exception, or free-form LLM prose
    beyond what a specific test needs) -- this is what ends up in the
    machine-readable report, so nothing here may ever be a secret, an API
    key, a system prompt, or a stack trace.
    """

    subsystem: str
    case_id: str
    description: str
    passed: bool
    message: str = ""
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "passed": self.passed,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass(frozen=True)
class MalformedCaseError(Exception):
    """Raised by a dataset loader when a case is structurally invalid
    (missing a required field, an empty case list, a duplicate case_id)
    -- surfaced as a loud, immediate error rather than a silently skipped
    case, since a dataset is the ground truth this whole harness depends
    on being trustworthy.
    """

    message: str

    def __str__(self) -> str:
        return self.message


def require_unique_case_ids(case_ids: list[str], dataset_name: str) -> None:
    seen: set[str] = set()
    for case_id in case_ids:
        if not case_id:
            raise MalformedCaseError(f"{dataset_name}: a case has an empty case_id")
        if case_id in seen:
            raise MalformedCaseError(f"{dataset_name}: duplicate case_id {case_id!r}")
        seen.add(case_id)


def require_non_empty(cases: list, dataset_name: str) -> None:
    if not cases:
        raise MalformedCaseError(f"{dataset_name}: dataset is empty")


def dumps_safe(results: list[EvalResult]) -> str:
    """Serialize a result list, verifying it's actually JSON-safe rather
    than trusting that it is -- catches an accidental non-primitive
    (e.g. a raw exception object) landing in ``expected``/``actual``
    before it can reach a report file.
    """
    return json.dumps([r.to_dict() for r in results], indent=2, default=str)


@dataclass
class SubsystemSummary:
    subsystem: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "failures": self.failures,
        }


def summarize(subsystem: str, results: list[EvalResult]) -> SubsystemSummary:
    summary = SubsystemSummary(subsystem=subsystem, total=len(results))
    for result in results:
        if result.passed:
            summary.passed += 1
        else:
            summary.failed += 1
            summary.failures.append(
                {"case_id": result.case_id, "description": result.description, "message": result.message}
            )
    return summary
