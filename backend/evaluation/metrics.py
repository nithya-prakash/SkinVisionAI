"""Reusable evaluation metrics.

Every function here is a plain, deterministic computation over already-
collected results -- nothing here calls a deterministic engine, an LLM,
or the agent. Metrics are reported *per subsystem*, never combined into
one artificial "AI accuracy" number: a 100% ingredient-parsing pass rate
and an 80% agent-grounding pass rate mean very different things, and
averaging them would hide exactly the failure a reader most needs to see.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from evaluation.runners.base import EvalResult


def pass_rate(results: Sequence[EvalResult]) -> float:
    """Fraction of cases that passed, in [0.0, 1.0]. Used for exact-match
    accuracy, safety pass rate, tool-selection accuracy, and grounding
    pass rate alike -- the *meaning* of "passed" is decided by how each
    runner constructs its ``EvalResult``s, not by this function.
    """
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def field_level_accuracy(actual: dict, expected: dict, fields: Sequence[str]) -> float:
    """Fraction of ``fields`` where ``actual[field] == expected[field]``.

    For structured results where only some fields are meaningful to
    compare (e.g. a routine result's ``suggested_am`` order without
    demanding every incidental field match) rather than requiring exact
    equality of the entire structure.
    """
    if not fields:
        return 1.0
    matches = sum(1 for f in fields if actual.get(f) == expected.get(f))
    return matches / len(fields)


def assert_deterministic(fn: Callable[[], Any], repeats: int = 3) -> tuple[bool, str]:
    """Call ``fn`` ``repeats`` times and confirm every call returns an
    identical (``==``) result. Returns ``(ok, message)`` rather than
    raising, so a caller can fold this into an ``EvalResult`` like any
    other check.
    """
    if repeats < 2:
        raise ValueError("repeats must be >= 2 to prove anything about determinism")
    results = [fn() for _ in range(repeats)]
    first = results[0]
    for i, r in enumerate(results[1:], start=2):
        if r != first:
            return False, f"run 1 and run {i} produced different results: {first!r} != {r!r}"
    return True, f"identical result across {repeats} runs"


def overall_counts(subsystem_summaries: dict[str, Any]) -> dict[str, int]:
    """Sum ``total``/``passed``/``failed`` across every subsystem summary
    dict (each already produced by ``evaluation.runners.base.summarize``)
    -- the plain aggregate the top-level report needs, not a percentage
    that implies anything beyond "how many of these engineering checks
    passed."
    """
    total = sum(s["total"] for s in subsystem_summaries.values())
    passed = sum(s["passed"] for s in subsystem_summaries.values())
    failed = sum(s["failed"] for s in subsystem_summaries.values())
    return {"total": total, "passed": passed, "failed": failed}
