"""The structured tool-call trace.

One ``ToolCallTraceEntry`` per tool call the agent loop actually
executed (deduplicated repeats reuse an earlier entry's result rather
than adding a new one -- see ``app.agent.agent``). This is what makes
"how did SkinVision AI reach this answer" reconstructable rather than
re-generated prose: the frontend can render ``tool_name`` +
``arguments`` + ``result`` directly, with no LLM involved in that
rendering at all.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Bounded so one oversized tool result can never make the trace (or what
# gets fed back to the LLM) grow without limit. See
# ``Settings.agent_max_tool_result_chars`` / docs/agent.md.
_TRUNCATION_NOTE = "Result truncated: exceeded the configured size limit."


class ToolCallTraceEntry(BaseModel):
    """One recorded tool call."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    call_index: int = Field(ge=0)
    success: bool
    error: str | None = None


def bound_tool_result(result: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Return ``result`` unchanged if its JSON serialization fits within
    ``max_chars``; otherwise a small, structured, always-valid stand-in --
    never a mid-string cut that would produce invalid JSON downstream.
    """
    serialized = json.dumps(result)
    if len(serialized) <= max_chars:
        return result
    return {
        "truncated": True,
        "original_char_count": len(serialized),
        "note": _TRUNCATION_NOTE,
    }
