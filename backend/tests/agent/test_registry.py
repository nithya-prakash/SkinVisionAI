"""Tests for app.agent.registry: ToolRegistry and execute_tool.

No network, no LLM, no database -- pure in-memory registration/execution.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agent.registry import ToolDefinition, ToolRegistry, execute_tool
from app.agent.tools import build_tool_registry


class _EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)


class _EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


def _echo_tool() -> ToolDefinition:
    return ToolDefinition(
        name="echo",
        description="Echoes its input back.",
        input_model=_EchoInput,
        output_model=_EchoOutput,
        handler=lambda input_: _EchoOutput(text=input_.text),
    )


# --- ToolRegistry ---


def test_register_and_get_known_tool() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    assert registry.get("echo") is not None
    assert "echo" in registry
    assert registry.names() == ["echo"]


def test_get_unknown_tool_returns_none() -> None:
    registry = ToolRegistry()
    assert registry.get("does_not_exist") is None
    assert "does_not_exist" not in registry


def test_duplicate_registration_raises() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_echo_tool())


def test_specs_reflect_input_model_schema() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    specs = registry.specs()
    assert len(specs) == 1
    assert specs[0].name == "echo"
    assert specs[0].input_schema == _EchoInput.model_json_schema()


def test_default_registry_has_five_tools() -> None:
    registry = build_tool_registry()
    assert registry.names() == sorted(
        [
            "analyze_product",
            "analyze_routine",
            "check_ingredient_compatibility",
            "compare_products",
            "get_ingredient_information",
        ]
    )


def test_default_registry_is_independent_per_call() -> None:
    a = build_tool_registry()
    b = build_tool_registry()
    assert a is not b
    # Registering an extra tool on one must never affect the other.
    a.register(_echo_tool())
    assert "echo" in a
    assert "echo" not in b


# --- execute_tool ---


def test_execute_tool_valid_arguments() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    result = execute_tool(registry, "echo", {"text": "hello"})
    assert result.success is True
    assert result.result == {"text": "hello"}
    assert result.error is None


def test_execute_tool_unknown_tool_rejected_cleanly() -> None:
    registry = ToolRegistry()
    result = execute_tool(registry, "execute_python", {"code": "print(1)"})
    assert result.success is False
    assert result.result is None
    assert "unknown tool" in result.error


def test_execute_tool_missing_required_argument_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    result = execute_tool(registry, "echo", {})
    assert result.success is False
    assert "invalid arguments" in result.error


def test_execute_tool_wrong_type_argument_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    # A list can never coerce to `str` under pydantic v2's default (lax)
    # validation, so this reliably exercises the wrong-type rejection path.
    result = execute_tool(registry, "echo", {"text": ["not", "a", "string"]})
    assert result.success is False
    assert "invalid arguments" in result.error


def test_execute_tool_extra_field_rejected() -> None:
    registry = ToolRegistry()
    registry.register(_echo_tool())
    result = execute_tool(registry, "echo", {"text": "hi", "unexpected": "field"})
    assert result.success is False
    assert "invalid arguments" in result.error


def test_execute_tool_handler_exception_reported_not_raised() -> None:
    registry = ToolRegistry()

    def _boom(_input: _EchoInput) -> _EchoOutput:
        raise RuntimeError("boom")

    registry.register(
        ToolDefinition(
            name="boom",
            description="Always fails.",
            input_model=_EchoInput,
            output_model=_EchoOutput,
            handler=_boom,
        )
    )
    result = execute_tool(registry, "boom", {"text": "x"})
    assert result.success is False
    assert result.error == "This tool failed to execute. The error has been logged."


def test_execute_tool_handler_exception_never_leaks_raw_exception_text() -> None:
    """A handler's internal exception text must never reach the caller --
    this trace entry is persisted and returned to the client via chat
    history (app.schemas.chat.ChatMessageRead.tool_trace).
    """
    registry = ToolRegistry()

    def _boom(_input: _EchoInput) -> _EchoOutput:
        raise RuntimeError("boom: /etc/shadow secret-db-password leaked-detail")

    registry.register(
        ToolDefinition(
            name="boom",
            description="Always fails.",
            input_model=_EchoInput,
            output_model=_EchoOutput,
            handler=_boom,
        )
    )
    result = execute_tool(registry, "boom", {"text": "x"})
    assert result.success is False
    assert "boom" not in result.error
    assert "/etc/shadow" not in result.error
    assert "secret-db-password" not in result.error
    assert "leaked-detail" not in result.error
