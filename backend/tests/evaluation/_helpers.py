"""Shared helper for turning a list[EvalResult] into a readable pytest
failure message -- not a test module itself (leading underscore keeps
pytest from collecting it as one).
"""
from __future__ import annotations

from evaluation.runners.base import EvalResult


def format_failures(results: list[EvalResult]) -> str:
    failed = [r for r in results if not r.passed]
    if not failed:
        return ""
    lines = [f"{len(failed)}/{len(results)} case(s) failed:"]
    for r in failed:
        lines.append(f"  - {r.case_id}: {r.message}")
    return "\n".join(lines)


def assert_all_passed(results: list[EvalResult]) -> None:
    assert all(r.passed for r in results), format_failures(results)
