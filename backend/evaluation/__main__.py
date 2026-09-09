"""Run the full evaluation suite and write a JSON report.

    python -m evaluation

Fully offline by default: every subsystem here uses FakeLLMProvider or a
pure deterministic engine call -- no network, no Anthropic/OpenAI API
key required. Exits non-zero if any case failed, so this is safe to wire
into CI as a regression gate.
"""
from __future__ import annotations

import asyncio
import sys

from evaluation.report import SubsystemRun, build_report, print_summary, write_report
from evaluation.runners import (
    agent_runner,
    comparison_runner,
    ingredients_runner,
    llm_runner,
    routine_runner,
    safety_runner,
    vision_runner,
)


async def _collect() -> list[SubsystemRun]:
    # Sync runners first (fast, no event loop needed internally).
    runs = [
        SubsystemRun("vision", vision_runner.run()),
        SubsystemRun("ingredients", ingredients_runner.run()),
        SubsystemRun("routine", routine_runner.run()),
        SubsystemRun("comparison", comparison_runner.run()),
    ]
    # Async runners (LLM/agent/safety all drive FakeLLMProvider coroutines).
    runs.append(SubsystemRun("llm", await llm_runner.run()))
    runs.append(SubsystemRun("agent", await agent_runner.run()))
    runs.append(SubsystemRun("safety", await safety_runner.run()))
    return runs


def main() -> int:
    subsystem_runs = asyncio.run(_collect())
    report = build_report(subsystem_runs, offline=True)
    print_summary(report)
    path = write_report(report)
    print(f"\nReport written to {path}")

    if report["overall"]["failed"] > 0:
        print(f"\n{report['overall']['failed']} case(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
