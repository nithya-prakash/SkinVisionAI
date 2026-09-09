"""The bounded agent tool-calling loop.

``while tool_call_requested: validate -> execute deterministic tool ->
append result`` until the model calls "provide_final_answer", or a hard
limit is hit -- see ``Settings.agent_max_turns`` /
``Settings.agent_max_tool_calls``. Database-free and independently
testable; ``app.services.agent_service`` wraps this with chat-session
persistence. Given the same provider script and inputs, always produces
the same trace and result -- no randomness, no hidden state.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.agent.prompts import AGENT_SYSTEM_PROMPT
from app.agent.registry import ToolRegistry, execute_tool
from app.agent.schemas import AgentFinalAnswerLLMOutput, AgentStatus, Citation
from app.agent.trace import ToolCallTraceEntry, bound_tool_result
from app.agent.validation import HallucinationError, validate_agent_answer
from app.config import Settings
from app.llm.base import (
    ConversationTurn,
    LLMAuthenticationError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    ToolCallRequest,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentLoopResult:
    """Everything ``app.services.agent_service`` needs to build the public
    ``AgentResponse`` -- deliberately not the API schema itself, since
    ``chat_session_id``/``message_id`` are only known after persistence.
    """

    status: AgentStatus
    answer: str
    tool_trace: list[ToolCallTraceEntry]
    citations: list[Citation]
    limitations: list[str]
    error: str | None = None


def _safe_error_message(exc: Exception) -> str:
    """A short, generic, user-safe message -- never the raw provider
    exception text, which could carry account/request details.
    """
    if isinstance(exc, LLMAuthenticationError):
        return "The AI assistant is currently unavailable (provider authentication issue)."
    if isinstance(exc, LLMRateLimitError):
        return "The AI assistant is currently unavailable (rate limited); please try again shortly."
    if isinstance(exc, LLMTimeoutError):
        return "The AI assistant is currently unavailable (the request timed out)."
    if isinstance(exc, LLMResponseValidationError):
        return "The AI assistant is currently unavailable (the response could not be validated)."
    return "The AI assistant is currently unavailable."


def _dedup_key(tool_name: str, arguments: dict[str, Any]) -> str:
    return f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"


def _walk_for_citations(obj: Any, seen: dict[str, str | None]) -> None:
    if isinstance(obj, dict):
        source = obj.get("source")
        if isinstance(source, str) and source and source not in seen:
            url = obj.get("source_url")
            seen[source] = url if isinstance(url, str) else None
        for value in obj.values():
            _walk_for_citations(value, seen)
    elif isinstance(obj, list):
        for item in obj:
            _walk_for_citations(item, seen)


def _extract_citations(trace: list[ToolCallTraceEntry]) -> list[Citation]:
    seen: dict[str, str | None] = {}
    for entry in trace:
        if entry.success and entry.result is not None:
            _walk_for_citations(entry.result, seen)
    return [Citation(source=source, source_url=url) for source, url in seen.items()]


def _extract_limitations(trace: list[ToolCallTraceEntry]) -> list[str]:
    seen: list[str] = []
    for entry in trace:
        if not (entry.success and entry.result is not None):
            continue
        items = entry.result.get("limitations")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and item not in seen:
                    seen.append(item)
    return seen


async def run_agent(
    *,
    user_message: str,
    prior_turns: list[ConversationTurn],
    provider: LLMProvider,
    registry: ToolRegistry,
    settings: Settings,
    seed_trace: list[ToolCallTraceEntry] | None = None,
) -> AgentLoopResult:
    """Run the bounded tool-calling loop for one user turn.

    ``prior_turns`` are earlier turns of a persisted conversation, already
    converted to plain ``user``/``assistant_text`` ``ConversationTurn``s by
    ``app.services.agent_service`` -- this turn's own tool-call/
    tool-result turns exist only locally within this call, never persisted
    or replayed across requests (see docs/agent.md's conversational-memory
    section for why that scope is deliberate).

    ``seed_trace`` (Phase 8) is context already established before this
    turn started -- e.g. a chat session linked to an existing analysis
    (``ChatSession.skin_analysis_id`` etc., see
    ``app.services.agent_service``). Each entry is treated exactly like a
    real tool call that already ran: included in the returned trace and
    ground truth from the start, and materialized as a
    ``tool_call``/``tool_result`` turn pair *before* the new user turn so
    the model sees it as established context without spending a real
    tool call on it. If the model asks for the same tool+arguments again
    anyway, the existing deduplication cache (seeded from these entries
    too) reuses the seeded result rather than re-executing.
    """
    seed = seed_trace or []
    history: list[ConversationTurn] = list(prior_turns)
    for entry in seed:
        seed_call_id = f"seed-{entry.call_index}"
        history.append(
            ConversationTurn(
                kind="tool_call",
                tool_call=ToolCallRequest(
                    call_id=seed_call_id, tool_name=entry.tool_name, arguments=entry.arguments
                ),
            )
        )
        history.append(
            ConversationTurn(
                kind="tool_result",
                call_id=seed_call_id,
                result=entry.result if entry.success else {"error": entry.error},
            )
        )
    history.append(ConversationTurn(kind="user", content=user_message))

    trace: list[ToolCallTraceEntry] = list(seed)
    cache: dict[str, ToolCallTraceEntry] = {_dedup_key(e.tool_name, e.arguments): e for e in seed}
    tool_call_count = 0

    for _turn in range(settings.agent_max_turns):
        try:
            response = await provider.generate_with_tools(
                AGENT_SYSTEM_PROMPT, history, registry.specs(), AgentFinalAnswerLLMOutput
            )
        except LLMProviderError as exc:
            logger.warning("agent_llm_unavailable error_type=%s", type(exc).__name__)
            return AgentLoopResult(
                status=AgentStatus.LLM_UNAVAILABLE,
                answer="",
                tool_trace=trace,
                citations=_extract_citations(trace),
                limitations=_extract_limitations(trace),
                error=_safe_error_message(exc),
            )

        if response.tool_call is not None:
            call = response.tool_call

            if tool_call_count >= settings.agent_max_tool_calls:
                logger.info("agent_max_tool_calls_reached count=%s", tool_call_count)
                return AgentLoopResult(
                    status=AgentStatus.MAX_TOOL_CALLS,
                    answer=(
                        "I reached the maximum number of tool calls allowed for one request "
                        "before I could finish. Here is what I found so far."
                    ),
                    tool_trace=trace,
                    citations=_extract_citations(trace),
                    limitations=_extract_limitations(trace),
                )

            key = _dedup_key(call.tool_name, call.arguments)
            entry = cache.get(key)
            if entry is None:
                exec_result = execute_tool(registry, call.tool_name, call.arguments)
                tool_call_count += 1
                bounded_result = (
                    bound_tool_result(exec_result.result, settings.agent_max_tool_result_chars)
                    if exec_result.success and exec_result.result is not None
                    else None
                )
                entry = ToolCallTraceEntry(
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    result=bounded_result,
                    call_index=len(trace),
                    success=exec_result.success,
                    error=exec_result.error,
                )
                trace.append(entry)
                cache[key] = entry

            history.append(ConversationTurn(kind="tool_call", tool_call=call))
            history.append(
                ConversationTurn(
                    kind="tool_result",
                    call_id=call.call_id,
                    result=entry.result if entry.success else {"error": entry.error},
                )
            )
            continue

        final = response.final_answer
        assert final is not None  # AgentLLMResponse guarantees exactly one of the two is set
        try:
            validate_agent_answer(final, trace)
        except HallucinationError as exc:
            logger.warning("agent_answer_rejected code=%s", exc.code)
            return AgentLoopResult(
                status=AgentStatus.VALIDATION_ERROR,
                answer="",
                tool_trace=trace,
                citations=_extract_citations(trace),
                limitations=_extract_limitations(trace),
                error=(
                    "The AI assistant's answer did not pass validation and was not returned. "
                    "The tool results below are unaffected and trustworthy."
                ),
            )

        return AgentLoopResult(
            status=AgentStatus.SUCCESS,
            answer=final.answer,
            tool_trace=trace,
            citations=_extract_citations(trace),
            limitations=list(dict.fromkeys([*_extract_limitations(trace), *final.limitations])),
        )

    logger.info("agent_max_turns_reached turns=%s", settings.agent_max_turns)
    if trace and not any(entry.success for entry in trace):
        return AgentLoopResult(
            status=AgentStatus.TOOL_ERROR,
            answer="I wasn't able to complete any of the requested lookups. Please try rephrasing your question.",
            tool_trace=trace,
            citations=[],
            limitations=[],
        )
    return AgentLoopResult(
        status=AgentStatus.MAX_TOOL_CALLS,
        answer=(
            "I reached the maximum number of steps allowed for one request before I could "
            "finish. Here is what I found so far."
        ),
        tool_trace=trace,
        citations=_extract_citations(trace),
        limitations=_extract_limitations(trace),
    )
