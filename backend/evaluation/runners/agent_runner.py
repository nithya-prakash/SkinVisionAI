"""Runs the agent evaluation dataset against the real Phase 7 bounded
loop (app.agent.agent.run_agent) with the real ToolRegistry
(app.agent.tools.build_tool_registry) -- never a second, parallel
implementation of dispatch/validation/limits. Fully offline: no network,
no API key.
"""
from __future__ import annotations

from app.agent.agent import run_agent
from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.agent.tools import build_tool_registry
from app.config import Settings
from app.llm.base import AgentLLMResponse, ToolCallRequest
from app.llm.provider import FakeLLMProvider
from evaluation.datasets.agent import (
    GROUNDING_CASES,
    NO_TOOL_NECESSARY_CASES,
    TOOL_SAFETY_CASES,
    TOOL_SELECTION_CASES,
)
from evaluation.runners.base import EvalResult, require_non_empty, require_unique_case_ids

SUBSYSTEM = "agent"
REGISTRY = build_tool_registry()
SETTINGS = Settings()


async def _run_agent(user_message: str, script: tuple | None, settings: Settings | None = None):
    provider = FakeLLMProvider(agent_script=list(script) if script is not None else None)
    return await run_agent(
        user_message=user_message,
        prior_turns=[],
        provider=provider,
        registry=REGISTRY,
        settings=settings or SETTINGS,
    )


async def _run_tool_selection_cases() -> list[EvalResult]:
    require_non_empty(list(TOOL_SELECTION_CASES), "agent.TOOL_SELECTION_CASES")
    require_unique_case_ids([c.case_id for c in TOOL_SELECTION_CASES], "agent.TOOL_SELECTION_CASES")

    results: list[EvalResult] = []
    for case in TOOL_SELECTION_CASES:
        script = case.script if case.scripted else None
        result = await _run_agent(case.user_message, script)
        actual_tool = result.tool_trace[0].tool_name if result.tool_trace else None
        passed = actual_tool == case.expect_tool_name
        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=passed,
                message="" if passed else f"expected tool {case.expect_tool_name!r}, got {actual_tool!r}",
                expected=case.expect_tool_name,
                actual=actual_tool,
            )
        )
    return results


async def _run_no_tool_necessary_cases() -> list[EvalResult]:
    require_non_empty(list(NO_TOOL_NECESSARY_CASES), "agent.NO_TOOL_NECESSARY_CASES")
    require_unique_case_ids([c.case_id for c in NO_TOOL_NECESSARY_CASES], "agent.NO_TOOL_NECESSARY_CASES")

    results: list[EvalResult] = []
    for case in NO_TOOL_NECESSARY_CASES:
        result = await _run_agent(case.user_message, case.script)
        passed = len(result.tool_trace) == 0
        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=passed,
                message="" if passed else f"expected zero tool calls, got {len(result.tool_trace)}",
                expected=0,
                actual=len(result.tool_trace),
            )
        )
    return results


async def _run_grounding_cases() -> list[EvalResult]:
    require_non_empty(list(GROUNDING_CASES), "agent.GROUNDING_CASES")
    require_unique_case_ids([c.case_id for c in GROUNDING_CASES], "agent.GROUNDING_CASES")

    results: list[EvalResult] = []
    for case in GROUNDING_CASES:
        result = await _run_agent("evaluation grounding case", case.script)
        actual_status = result.status.value
        passed = actual_status == case.expect_status
        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=passed,
                message="" if passed else f"expected status={case.expect_status!r}, got {actual_status!r}",
                expected=case.expect_status,
                actual=actual_status,
            )
        )
    return results


async def _run_tool_safety_cases() -> list[EvalResult]:
    require_non_empty(list(TOOL_SAFETY_CASES), "agent.TOOL_SAFETY_CASES")
    require_unique_case_ids([c.case_id for c in TOOL_SAFETY_CASES], "agent.TOOL_SAFETY_CASES")

    results: list[EvalResult] = []
    for case in TOOL_SAFETY_CASES:
        result = await _run_agent("evaluation tool-safety case", case.script)
        failures = []
        actual_status = result.status.value
        if actual_status != case.expect_status:
            failures.append(f"expected status={case.expect_status!r}, got {actual_status!r}")
        if case.expect_tool_call_failed_at_index is not None:
            idx = case.expect_tool_call_failed_at_index
            if idx >= len(result.tool_trace) or result.tool_trace[idx].success:
                failures.append(f"expected tool_trace[{idx}] to have failed safely, but it didn't")
        # Never a fabricated success: a failed entry's result must be None.
        for entry in result.tool_trace:
            if not entry.success and entry.result is not None:
                failures.append(f"tool_trace entry {entry.tool_name!r} failed but has a non-None result")

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                actual={
                    "status": actual_status,
                    "tool_trace": [(e.tool_name, e.success) for e in result.tool_trace],
                },
            )
        )
    return results


async def _run_tool_call_limit_case() -> EvalResult:
    settings = Settings(agent_max_tool_calls=3, agent_max_turns=20)
    ingredients = ["retinol", "niacinamide", "salicylic acid", "glycolic acid", "vitamin c", "hyaluronic acid"]
    script = [
        AgentLLMResponse(
            tool_call=ToolCallRequest(
                call_id=f"c{i}", tool_name="get_ingredient_information", arguments={"ingredient": name}
            ),
            final_answer=None,
        )
        for i, name in enumerate(ingredients)
    ]
    result = await _run_agent("evaluation tool-call-limit case", tuple(script), settings)
    failures = []
    if result.status.value != "max_tool_calls":
        failures.append(f"expected status=max_tool_calls, got {result.status.value!r}")
    if len(result.tool_trace) != 3:
        failures.append(f"expected exactly 3 executed tool calls (AGENT_MAX_TOOL_CALLS=3), got {len(result.tool_trace)}")
    return EvalResult(
        SUBSYSTEM,
        "agent_max_tool_calls_enforced",
        "6 distinct scripted tool requests against agent_max_tool_calls=3 stop at exactly 3",
        passed=not failures,
        message="; ".join(failures),
        actual={"status": result.status.value, "executed": len(result.tool_trace)},
    )


async def _run_tool_turn_limit_case() -> EvalResult:
    settings = Settings(agent_max_turns=2, agent_max_tool_calls=100)
    script = [
        AgentLLMResponse(
            tool_call=ToolCallRequest(call_id="c1", tool_name="get_ingredient_information", arguments={"ingredient": "retinol"}),
            final_answer=None,
        ),
        AgentLLMResponse(
            tool_call=ToolCallRequest(call_id="c2", tool_name="get_ingredient_information", arguments={"ingredient": "niacinamide"}),
            final_answer=None,
        ),
        AgentLLMResponse(
            tool_call=None,
            final_answer=AgentFinalAnswerLLMOutput(answer="never reached", key_points=[], limitations=[]),
        ),
    ]
    result = await _run_agent("evaluation turn-limit case", tuple(script), settings)
    passed = len(result.tool_trace) == 2
    return EvalResult(
        SUBSYSTEM,
        "agent_max_turns_enforced",
        "agent_max_turns=2 stops the loop after 2 turns even though a 3rd scripted step exists",
        passed=passed,
        message="" if passed else f"expected exactly 2 executed tool calls, got {len(result.tool_trace)}",
        actual=len(result.tool_trace),
    )


def _run_bounded_tool_result_case() -> EvalResult:
    """Directly unit-tests app.agent.trace.bound_tool_result rather than
    trying to coax one of the 5 real tools into producing an oversized
    result through plausible input -- the bounding logic itself is what
    needs proving, and it's a pure function independent of which tool
    produced the oversized dict.
    """
    from app.agent.trace import bound_tool_result

    huge = {"interactions": [{"note": "x" * 100} for _ in range(500)]}
    import json

    original_size = len(json.dumps(huge))
    bounded = bound_tool_result(huge, max_chars=1000)
    failures = []
    if len(json.dumps(bounded)) > 1000 + 200:  # generous margin for the stand-in's own overhead
        failures.append("bounded result still exceeds the character limit by a wide margin")
    if bounded == huge:
        failures.append("an oversized result was returned unchanged instead of bounded")
    if not isinstance(bounded, dict):
        failures.append("bounded result is not a dict -- would break downstream JSON serialization")

    small = {"a": 1}
    if bound_tool_result(small, max_chars=1000) != small:
        failures.append("a small, in-bounds result was altered when it should have been returned unchanged")

    return EvalResult(
        SUBSYSTEM,
        "agent_tool_result_size_is_bounded",
        f"An oversized tool result ({original_size} chars) is replaced with a small, valid stand-in; a small result is untouched",
        passed=not failures,
        message="; ".join(failures),
    )


async def _run_determinism_case() -> EvalResult:
    script = (
        _mk_call("check_ingredient_compatibility", {"ingredients": ["retinol", "glycolic acid"]}),
        _mk_final("Retinol and glycolic acid have a documented caution-level interaction."),
    )

    async def compute() -> tuple:
        result = await _run_agent("evaluation determinism case", script)
        return (
            result.status.value,
            tuple((e.tool_name, e.success) for e in result.tool_trace),
            result.answer,
        )

    # assert_deterministic (evaluation.metrics) is sync-only, since every
    # other subsystem's determinism check calls a sync function -- the
    # agent loop is async, so this repeats the same 3-run comparison by
    # hand rather than forcing metrics.py to grow an async variant for
    # one caller.
    first = await compute()
    ok = True
    message = "identical result across 3 runs"
    for i in range(2, 4):
        again = await compute()
        if again != first:
            ok = False
            message = f"run 1 and run {i} produced different results"
            break

    return EvalResult(
        SUBSYSTEM,
        "agent_loop_is_deterministic",
        "The same scripted scenario run 3 times produces an identical status/trace/answer",
        passed=ok,
        message=message,
    )


def _mk_call(tool_name: str, arguments: dict) -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=ToolCallRequest(call_id="c1", tool_name=tool_name, arguments=arguments), final_answer=None
    )


def _mk_final(answer: str) -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=None, final_answer=AgentFinalAnswerLLMOutput(answer=answer, key_points=[], limitations=[])
    )


async def run() -> list[EvalResult]:
    results: list[EvalResult] = []
    results.extend(await _run_tool_selection_cases())
    results.extend(await _run_no_tool_necessary_cases())
    results.extend(await _run_grounding_cases())
    results.extend(await _run_tool_safety_cases())
    results.append(await _run_tool_call_limit_case())
    results.append(await _run_tool_turn_limit_case())
    results.append(_run_bounded_tool_result_case())
    results.append(await _run_determinism_case())
    return results
