"""The tool registry and tool execution.

Security-critical module: this is the *only* place a tool call the LLM
requested turns into an actual Python call, and it does so by an exact
string lookup into a dict populated at startup by
``app.agent.tools.build_tool_registry()`` -- never ``eval``, ``exec``,
``importlib``, ``getattr`` on an arbitrary name, or any other
reflection-based dispatch. A tool name the registry doesn't recognize is
rejected before any code runs; arguments are always Pydantic-validated
against the tool's declared input model before its handler is called.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.llm.base import ToolSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolDefinition:
    """One agent tool. ``handler`` must be a pure, synchronous,
    side-effect-free function of ``input_model`` -> ``output_model`` --
    every real tool wraps an existing deterministic engine call (Phase
    4/5), never new domain logic. ``deterministic=True`` documents that
    guarantee; it is not currently branched on, but exists so a future,
    explicitly-non-deterministic tool (if one is ever added) cannot be
    registered silently as if it were.
    """

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]
    deterministic: bool = True


@dataclass(frozen=True)
class ToolExecutionResult:
    """The outcome of one ``execute_tool`` call. Exactly one of
    ``result``/``error`` is meaningful, selected by ``success``.
    """

    success: bool
    result: dict | None
    error: str | None


class ToolRegistry:
    """A typed, name-keyed set of tools. The LLM can only ever "call" a
    tool that is present here.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        """The shape advertised to the LLM via native tool-calling --
        derived from each tool's real ``input_model``, so the schema the
        model sees can never drift from what execution actually
        validates against.
        """
        return [
            ToolSpec(name=t.name, description=t.description, input_schema=t.input_model.model_json_schema())
            for t in self._tools.values()
        ]


def execute_tool(registry: ToolRegistry, tool_name: str, raw_arguments: dict) -> ToolExecutionResult:
    """Validate and run one tool call. Never raises -- every failure mode
    (unknown tool, invalid/missing/wrong-typed arguments, an exception
    inside the handler) is reported back as
    ``ToolExecutionResult(success=False, error=...)`` so the agent loop
    can record it in the trace and continue (or stop) in a controlled way,
    per docs/agent.md's fail-safe error behavior.
    """
    tool = registry.get(tool_name)
    if tool is None:
        return ToolExecutionResult(success=False, result=None, error=f"unknown tool: {tool_name!r}")

    try:
        validated_input = tool.input_model.model_validate(raw_arguments)
    except ValidationError as exc:
        return ToolExecutionResult(success=False, result=None, error=f"invalid arguments: {exc}")

    try:
        output = tool.handler(validated_input)
    except Exception:  # defensive: a tool failure must never crash the agent loop
        # Never interpolate the raw exception into a client-visible field --
        # this trace entry is persisted and returned to the client via
        # chat history (app.schemas.chat.ChatMessageRead.tool_trace), so a
        # handler's internal exception text (which could contain a file
        # path, a DB error detail, or similar) must never reach it. Full
        # detail goes to the server-side log only, matching the global
        # exception handler's discipline (app/main.py).
        logger.exception("tool_execution_failed tool_name=%s", tool_name)
        return ToolExecutionResult(
            success=False,
            result=None,
            error="This tool failed to execute. The error has been logged.",
        )

    return ToolExecutionResult(success=True, result=output.model_dump(mode="json"), error=None)
