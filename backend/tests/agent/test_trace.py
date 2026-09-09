"""Tests for app.agent.trace: ToolCallTraceEntry and bound_tool_result."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agent.trace import ToolCallTraceEntry, bound_tool_result


def test_trace_entry_records_all_required_fields() -> None:
    entry = ToolCallTraceEntry(
        tool_name="check_ingredient_compatibility",
        arguments={"ingredients": ["retinol", "salicylic acid"]},
        result={"interactions": []},
        call_index=0,
        success=True,
        error=None,
    )
    assert entry.tool_name == "check_ingredient_compatibility"
    assert entry.call_index == 0
    assert entry.success is True
    assert entry.error is None


def test_trace_entry_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ToolCallTraceEntry(
            tool_name="x", call_index=0, success=True, unexpected_field="nope"
        )


def test_bound_tool_result_passes_small_result_through_unchanged() -> None:
    result = {"a": 1, "b": [1, 2, 3]}
    assert bound_tool_result(result, max_chars=10_000) == result


def test_bound_tool_result_truncates_oversized_result() -> None:
    big = {"data": "x" * 100}
    bounded = bound_tool_result(big, max_chars=50)
    assert bounded["truncated"] is True
    assert bounded["original_char_count"] > 50
    # Always JSON-serializable and small, regardless of input size.
    assert len(json.dumps(bounded)) < 200


def test_bound_tool_result_boundary_exact_length_not_truncated() -> None:
    result = {"x": "a"}
    exact_len = len(json.dumps(result))
    assert bound_tool_result(result, max_chars=exact_len) == result
    assert bound_tool_result(result, max_chars=exact_len - 1) != result
