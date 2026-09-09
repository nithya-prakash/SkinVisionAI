"""The LLM provider abstraction.

The rest of the application depends only on ``LLMProvider`` -- never on a
specific vendor's SDK or API shape. See ``provider.py`` for the concrete
implementations (Anthropic, an OpenAI-compatible HTTP client, and a
deterministic offline fake) and ``docs/llm.md`` for the full architecture.

The LLM is an explanation/orchestration layer only. It never determines
ingredient identity, compatibility, severity, or routine ordering --
those remain the deterministic Python engines' exclusive responsibility
(Phases 1-5). This module's interface reflects that: a provider's only
job is to turn an already-validated, already-authoritative structured
input into a structured, schema-validated narrative response.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


class LLMProviderError(Exception):
    """Base class for all LLM provider failures.

    The API layer catches this (and only this family of exceptions) to
    degrade gracefully -- the deterministic analysis is still returned
    even when the explanation layer fails. Never let a raw provider SDK
    exception (which may carry request headers, account details, etc.)
    escape past a provider implementation.
    """


class LLMAuthenticationError(LLMProviderError):
    """The provider rejected the request due to a missing/invalid API key."""


class LLMRateLimitError(LLMProviderError):
    """The provider is rate-limiting this application."""


class LLMTimeoutError(LLMProviderError):
    """The provider did not respond within the configured timeout."""


class LLMUnavailableError(LLMProviderError):
    """A connectivity or provider-side failure not covered above."""


class LLMResponseValidationError(LLMProviderError):
    """The provider's raw output could not be parsed into the requested
    Pydantic schema (malformed JSON, missing required fields, etc.).

    Distinct from ``app.llm.validation.HallucinationError``: this is a
    *shape* failure (the response isn't even valid ``response_model``
    data); hallucination checking only runs on output that already
    passed this schema validation.
    """


class LLMProvider(ABC):
    """Abstract interface every LLM provider implementation satisfies."""

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        input_data: dict,
        response_model: type[ResponseModel],
    ) -> ResponseModel:
        """Ask the model to produce output matching ``response_model``.

        ``input_data`` is the full deterministic context (already-computed
        analysis results) serialized as JSON-safe plain data -- the model
        never receives anything else, and is instructed (via
        ``system_prompt``) to explain only what's present in it.

        Returns a validated instance of ``response_model``. Raises an
        ``LLMProviderError`` subclass for any failure (auth, timeout, rate
        limit, malformed output, or general unavailability) -- never lets
        a provider-specific exception type escape.
        """
        raise NotImplementedError

    async def generate_with_tools(
        self,
        system_prompt: str,
        history: list["ConversationTurn"],
        tools: list["ToolSpec"],
        response_model: type[ResponseModel],
    ) -> "AgentLLMResponse[ResponseModel]":
        """Ask the model to either call one tool or produce a final answer
        matching ``response_model`` (Phase 7's agent tool-calling
        extension -- additive to ``generate_structured`` above, which
        Phase 6's explanation layer keeps using unchanged).

        ``history`` is the full accumulated conversation so far in a
        provider-agnostic shape (``ConversationTurn``) -- each concrete
        provider converts it to its own wire format internally and holds
        no server-side conversation state itself; the caller (the agent
        loop in ``app.agent.agent``) is the only place state accumulates.

        ``tools`` are the domain tools currently available (from
        ``app.agent.registry.ToolRegistry``), passed via the provider's
        native structured tool/function-calling mechanism -- never
        represented as instructions to emit fake JSON in prose. A
        provider additionally always offers one synthetic
        "provide_final_answer" tool shaped by ``response_model``; the
        model calling that tool (instead of a domain tool) is how it
        signals "I'm done, here's my answer" and is reported back as
        ``AgentLLMResponse.final_answer`` rather than
        ``AgentLLMResponse.tool_call``.

        Raises the same ``LLMProviderError`` family as
        ``generate_structured`` on any provider failure. Not marked
        ``@abstractmethod`` (unlike ``generate_structured``) so this
        extension cannot silently break a provider written only against
        the Phase 6 interface; the default implementation here raises
        ``NotImplementedError``, and every provider actually used by the
        agent (Anthropic, OpenAI-compatible, fake) overrides it.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class ToolSpec:
    """One tool's shape, as advertised to the LLM. Built from a
    ``app.agent.registry.ToolDefinition`` -- never hand-authored, so the
    schema the model sees and the schema tool execution actually validates
    against can never drift apart.
    """

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCallRequest:
    """One tool call the model requested. ``call_id`` is the provider's
    own identifier for this specific call (an Anthropic ``tool_use`` block
    id, an OpenAI ``tool_call`` id, or a synthetic id from the fake
    provider) -- the agent loop treats it as an opaque token it must echo
    back unchanged when it later reports this call's result, and never
    interprets its content.
    """

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ConversationTurn:
    """One step of an agent conversation, in a shape every provider can
    translate to and from its own wire format. The agent loop is the only
    place that accumulates a list of these; providers are stateless per
    call and rebuild their native message list from this each time.

    - ``kind="user"``: ``content`` is a human/user message.
    - ``kind="assistant_text"``: ``content`` is a prior plain-text final
      answer (used only to replay earlier turns of a persisted
      conversation -- never produced mid-loop by the current turn).
    - ``kind="tool_call"``: ``tool_call`` is what the assistant requested.
    - ``kind="tool_result"``: ``call_id`` references the ``tool_call`` this
      answers; ``result`` is the JSON-safe tool output (or an
      ``{"error": ...}`` payload when the tool call failed).
    """

    kind: Literal["user", "assistant_text", "tool_call", "tool_result"]
    content: str | None = None
    tool_call: ToolCallRequest | None = None
    call_id: str | None = None
    result: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentLLMResponse(Generic[ResponseModel]):
    """What the model did on one ``generate_with_tools`` turn: exactly one
    of ``tool_call`` or ``final_answer`` is set, never both, never neither.
    """

    tool_call: ToolCallRequest | None
    final_answer: ResponseModel | None
