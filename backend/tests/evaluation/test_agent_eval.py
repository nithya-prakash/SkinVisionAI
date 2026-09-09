"""Runs the agent evaluation suite as a regular pytest test. Fully
offline: FakeLLMProvider only, no network, no API key.
"""
from __future__ import annotations

import pytest

from evaluation.datasets.agent import TOOL_SELECTION_CASES
from evaluation.metrics import pass_rate
from evaluation.runners import agent_runner
from tests.evaluation._helpers import assert_all_passed

pytestmark = pytest.mark.asyncio


async def test_agent_evaluation_suite_passes() -> None:
    results = await agent_runner.run()
    assert_all_passed(results)


async def test_agent_evaluation_has_no_duplicate_case_ids() -> None:
    results = await agent_runner.run()
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


async def test_agent_tool_selection_accuracy_is_100_percent() -> None:
    """The dedicated tool-selection accuracy metric, computed the same
    way ``python -m evaluation``'s report would -- a specific, named
    number for this specific property, not folded into the subsystem's
    overall pass rate.
    """
    results = await agent_runner.run()
    tool_selection_ids = {c.case_id for c in TOOL_SELECTION_CASES}
    tool_selection_results = [r for r in results if r.case_id in tool_selection_ids]
    assert len(tool_selection_results) == len(TOOL_SELECTION_CASES)
    assert pass_rate(tool_selection_results) == 1.0


async def test_agent_evaluation_covers_limits_and_unsafe_tool_requests() -> None:
    results = await agent_runner.run()
    ids = {r.case_id for r in results}
    assert any("max_tool_calls" in c for c in ids)
    assert any("max_turns" in c for c in ids)
    assert any("unknown_tool" in c for c in ids)
    assert any("malformed_arguments" in c for c in ids)
    assert any("bounded" in c for c in ids)


async def test_agent_evaluation_covers_grounding_including_zero_tool_call_case() -> None:
    results = await agent_runner.run()
    ids = {r.case_id for r in results}
    assert any("without_any_tool_call" in c for c in ids)
