"""Tests for app.agent.agent.run_agent: the bounded tool-calling loop.

Entirely offline -- every scenario drives a FakeLLMProvider via a
pre-programmed ``agent_script`` (a list of AgentLLMResponse steps), so
each test has exact, deterministic control over what the model "does"
without any text-guessing. No API key, no network, no database.
"""
from __future__ import annotations

import pytest

from app.agent.agent import run_agent
from app.agent.schemas import AgentFinalAnswerLLMOutput, AgentStatus
from app.agent.tools import build_tool_registry
from app.config import Settings
from app.llm.base import AgentLLMResponse, LLMTimeoutError, ToolCallRequest
from app.llm.provider import FakeLLMProvider

pytestmark = pytest.mark.asyncio


def _final(answer: str, **overrides) -> AgentLLMResponse:
    data = {"answer": answer, "key_points": [], "limitations": []}
    data.update(overrides)
    return AgentLLMResponse(tool_call=None, final_answer=AgentFinalAnswerLLMOutput(**data))


def _call(tool_name: str, arguments: dict, call_id: str = "call-1") -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=ToolCallRequest(call_id=call_id, tool_name=tool_name, arguments=arguments),
        final_answer=None,
    )


async def _run(script, settings: Settings | None = None):
    return await run_agent(
        user_message="test message",
        prior_turns=[],
        provider=FakeLLMProvider(agent_script=script),
        registry=build_tool_registry(),
        settings=settings or Settings(),
    )


# --- Scenario A: single ingredient-compatibility tool call, then answer ---


async def test_scenario_a_single_tool_call_then_final_answer() -> None:
    script = [
        _call("check_ingredient_compatibility", {"ingredients": ["retinol", "salicylic acid"]}),
        _final("Retinol and salicylic acid have a documented caution-level interaction."),
    ]
    result = await _run(script)
    assert result.status == AgentStatus.SUCCESS
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0].tool_name == "check_ingredient_compatibility"
    assert result.tool_trace[0].success is True
    assert result.tool_trace[0].result["interactions"][0]["severity"] == "caution"


# --- Scenario B: compare_products ---


async def test_scenario_b_compare_products_tool_call() -> None:
    script = [
        _call(
            "compare_products",
            {
                "product_a": {"name": "A", "raw_ingredient_text": "Retinol, Niacinamide"},
                "product_b": {"name": "B", "raw_ingredient_text": "Retinol, Salicylic Acid"},
            },
        ),
        _final("Both products share retinol; B also contains salicylic acid."),
    ]
    result = await _run(script)
    assert result.status == AgentStatus.SUCCESS
    assert result.tool_trace[0].tool_name == "compare_products"
    assert result.tool_trace[0].result["shared_ingredients"] == ["retinol"]


# --- Scenario C: analyze_routine ---


async def test_scenario_c_analyze_routine_tool_call() -> None:
    script = [
        _call(
            "analyze_routine",
            {"products": [{"product_name": "A", "raw_ingredients": "Retinol"}]},
        ),
        _final("Your routine has one product with no documented interactions."),
    ]
    result = await _run(script)
    assert result.status == AgentStatus.SUCCESS
    assert result.tool_trace[0].tool_name == "analyze_routine"


# --- Scenario D: unknown tool request ---


async def test_scenario_d_unknown_tool_request_rejected_and_loop_continues() -> None:
    script = [
        _call("execute_python", {"code": "import os"}),
        _final("I can't run arbitrary code, but I can check ingredient compatibility instead."),
    ]
    result = await _run(script)
    # The bad call is recorded (rejected), the model gets a chance to recover.
    assert result.tool_trace[0].tool_name == "execute_python"
    assert result.tool_trace[0].success is False
    assert "unknown tool" in result.tool_trace[0].error
    assert result.status == AgentStatus.SUCCESS


# --- Scenario E: fabricated result without calling the required tool ---


async def test_scenario_e_fabricated_answer_without_tool_call_rejected() -> None:
    script = [_final("Retinol and niacinamide are compatible and work well together.")]
    result = await _run(script)
    assert result.status == AgentStatus.VALIDATION_ERROR
    assert result.answer == ""
    assert result.error is not None


# --- Multi-tool reasoning ---


async def test_multi_tool_reasoning_three_products_then_routine() -> None:
    script = [
        _call("analyze_product", {"name": "A", "raw_ingredient_text": "Retinol"}, call_id="c1"),
        _call("analyze_product", {"name": "B", "raw_ingredient_text": "Niacinamide"}, call_id="c2"),
        _call("analyze_product", {"name": "C", "raw_ingredient_text": "Glycolic Acid"}, call_id="c3"),
        _call(
            "analyze_routine",
            {
                "products": [
                    {"product_name": "A", "raw_ingredients": "Retinol"},
                    {"product_name": "B", "raw_ingredients": "Niacinamide"},
                    {"product_name": "C", "raw_ingredients": "Glycolic Acid"},
                ]
            },
            call_id="c4",
        ),
        _final("Here is a suggested evening routine based on the three products."),
    ]
    result = await _run(script)
    assert result.status == AgentStatus.SUCCESS
    assert [e.tool_name for e in result.tool_trace] == [
        "analyze_product",
        "analyze_product",
        "analyze_product",
        "analyze_routine",
    ]


# --- Max tool calls ---


async def test_max_tool_calls_reached_stops_execution() -> None:
    settings = Settings(agent_max_tool_calls=2, agent_max_turns=10)
    script = [
        _call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c1"),
        _call("get_ingredient_information", {"ingredient": "niacinamide"}, call_id="c2"),
        _call("get_ingredient_information", {"ingredient": "salicylic acid"}, call_id="c3"),
        _final("done"),  # never reached
    ]
    result = await _run(script, settings)
    assert result.status == AgentStatus.MAX_TOOL_CALLS
    # Only 2 tools actually executed -- the 3rd request was rejected before running.
    assert len(result.tool_trace) == 2


async def test_max_tool_calls_holds_under_sustained_pressure() -> None:
    """Phase 10: the test above scripts exactly one call past the cap
    (3 requested against a cap of 2), which proves the boundary but not
    that the cap holds under sustained pressure. This scripts 6 *distinct*
    ingredient lookups (distinct arguments each time, so dedup can't
    collapse any of them into a cache hit) against a cap of 3, spanning
    enough turns to attempt all 6 if the cap were not enforced.
    """
    settings = Settings(agent_max_tool_calls=3, agent_max_turns=20)
    ingredients = [
        "retinol",
        "niacinamide",
        "salicylic acid",
        "glycolic acid",
        "vitamin c",
        "hyaluronic acid",
    ]
    script = [
        _call("get_ingredient_information", {"ingredient": name}, call_id=f"c{i}")
        for i, name in enumerate(ingredients)
    ] + [_final("done")]  # never reached
    result = await _run(script, settings)
    assert result.status == AgentStatus.MAX_TOOL_CALLS
    assert len(result.tool_trace) == 3
    # Every executed call actually ran (no fabricated successes) and each
    # is one of the first 3 scripted, distinct ingredients -- not a
    # repeat/cache artifact.
    executed_ingredients = [entry.arguments["ingredient"] for entry in result.tool_trace]
    assert executed_ingredients == ingredients[:3]
    assert all(entry.success for entry in result.tool_trace)


# --- Max turns ---


async def test_max_turns_reached_returns_controlled_response() -> None:
    settings = Settings(agent_max_turns=2, agent_max_tool_calls=100)
    script = [
        _call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c1"),
        _call("get_ingredient_information", {"ingredient": "niacinamide"}, call_id="c2"),
        _final("done"),  # never reached: only 2 turns allowed
    ]
    result = await _run(script, settings)
    # Both scripted tool calls succeeded, so the turn-limit fallback
    # reports MAX_TOOL_CALLS rather than TOOL_ERROR (reserved for when
    # every attempted call failed -- see the next test).
    assert result.status == AgentStatus.MAX_TOOL_CALLS
    assert len(result.tool_trace) == 2


# --- Tool failure ---


async def test_tool_failure_is_recorded_not_fabricated() -> None:
    script = [
        _call("check_ingredient_compatibility", {"not_a_real_field": True}, call_id="c1"),
        _final("I wasn't able to check that; could you list the ingredients again?"),
    ]
    result = await _run(script)
    assert result.tool_trace[0].success is False
    assert result.tool_trace[0].result is None
    assert result.status == AgentStatus.SUCCESS


async def test_all_calls_failing_until_max_turns_reports_tool_error() -> None:
    settings = Settings(agent_max_turns=2, agent_max_tool_calls=100)
    script = [
        _call("execute_python", {"code": "..."}, call_id="c1"),
        _call("import", {"module": "os"}, call_id="c2"),
    ]
    result = await _run(script, settings)
    assert result.status == AgentStatus.TOOL_ERROR
    assert all(not e.success for e in result.tool_trace)


# --- LLM failure ---


async def test_llm_unavailable_returns_controlled_status() -> None:
    result = await run_agent(
        user_message="hello",
        prior_turns=[],
        provider=FakeLLMProvider(raise_error=LLMTimeoutError("simulated timeout")),
        registry=build_tool_registry(),
        settings=Settings(),
    )
    assert result.status == AgentStatus.LLM_UNAVAILABLE
    assert result.error is not None
    assert "simulated timeout" not in result.error


async def test_llm_unavailable_mid_loop_after_a_successful_tool_call() -> None:
    script = [_call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c1")]
    provider = FakeLLMProvider(agent_script=script)
    # After the scripted step is exhausted, the fake raises a validation
    # error simulating an unexpected provider failure mid-loop.
    result = await run_agent(
        user_message="hello",
        prior_turns=[],
        provider=provider,
        registry=build_tool_registry(),
        settings=Settings(),
    )
    # The scripted single tool call ran, then the script ran out -- the
    # fake surfaces that as an LLMResponseValidationError, which is an
    # LLMProviderError subclass, so the loop reports LLM_UNAVAILABLE while
    # preserving the (successful) trace collected so far.
    assert result.status == AgentStatus.LLM_UNAVAILABLE
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0].success is True


# --- Deduplication ---


async def test_identical_repeated_tool_call_is_deduplicated() -> None:
    script = [
        _call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c1"),
        _call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c2"),
        _final("Retinol is a retinoid."),
    ]
    result = await _run(script)
    assert result.status == AgentStatus.SUCCESS
    # Only one trace entry despite two identical requests.
    assert len(result.tool_trace) == 1


async def test_different_arguments_are_not_deduplicated() -> None:
    script = [
        _call("get_ingredient_information", {"ingredient": "retinol"}, call_id="c1"),
        _call("get_ingredient_information", {"ingredient": "niacinamide"}, call_id="c2"),
        _final("Both are recognized ingredients."),
    ]
    result = await _run(script)
    assert len(result.tool_trace) == 2


# --- Determinism ---


async def test_same_script_and_input_produces_same_trace_and_result() -> None:
    def make_script():
        return [
            _call("check_ingredient_compatibility", {"ingredients": ["retinol", "glycolic acid"]}),
            _final("Retinol and glycolic acid have a documented caution-level interaction."),
        ]

    first = await _run(make_script())
    second = await _run(make_script())
    assert first.status == second.status == AgentStatus.SUCCESS
    assert first.answer == second.answer
    assert [e.model_dump() for e in first.tool_trace] == [e.model_dump() for e in second.tool_trace]
    assert [c.model_dump() for c in first.citations] == [c.model_dump() for c in second.citations]
