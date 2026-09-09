"""Concrete ``LLMProvider`` implementations.

- ``AnthropicProvider`` -- the real provider this project defaults to,
  using forced tool-use to get schema-validated structured output.
- ``OpenAICompatibleProvider`` -- a second real implementation (any
  OpenAI-compatible chat-completions endpoint), demonstrating that the
  application is not hard-coded to one vendor, per the project's
  provider-abstraction requirement.
- ``FakeLLMProvider`` -- deterministic, offline, no API key or network.
  Used by the full test suite and available as ``LLM_PROVIDER=fake`` for
  local development or CI/Docker verification without a real key.

``get_llm_provider(settings)`` is the one place that decides which
concrete class to instantiate -- every other module depends on the
``LLMProvider`` interface only. See docs/llm.md.
"""
from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.llm.base import (
    AgentLLMResponse,
    ConversationTurn,
    LLMAuthenticationError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
    ToolCallRequest,
    ToolSpec,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

_TOOL_NAME = "emit_structured_response"

# The synthetic tool every agent-capable provider always offers alongside
# the real domain tools -- the model calling this one (instead of a
# domain tool) is how it signals "I'm done, here's my final answer" via
# the same native structured tool-calling mechanism, never via free text
# the backend would have to parse/guess at. See ``app.llm.base.LLMProvider
# .generate_with_tools``.
_FINAL_ANSWER_TOOL_NAME = "provide_final_answer"
_FINAL_ANSWER_TOOL_DESCRIPTION = (
    "Call this when you have enough information to answer the user, "
    "instead of calling another tool. Do not call this before using a "
    "tool to ground any skincare-domain fact your answer depends on."
)


class AnthropicProvider(LLMProvider):
    """Uses the Anthropic Messages API with forced tool-use to obtain
    output matching an arbitrary Pydantic schema. Requires the
    ``anthropic`` package and a valid API key -- never imported or
    instantiated unless ``LLM_PROVIDER=anthropic`` is actually selected.
    """

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 30.0) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def generate_structured(
        self, system_prompt: str, input_data: dict, response_model: type[ResponseModel]
    ) -> ResponseModel:
        import anthropic

        schema = response_model.model_json_schema()
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(input_data)}],
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": "Emit the structured explanation response.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMAuthenticationError("Anthropic rejected the configured API key") from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError("Anthropic rate limit exceeded") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError("Anthropic request timed out") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not connect to Anthropic") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"Anthropic returned an error status: {exc.status_code}") from exc

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            raise LLMResponseValidationError("Anthropic response contained no tool_use block")

        try:
            return response_model.model_validate(tool_use_blocks[0].input)
        except ValidationError as exc:
            raise LLMResponseValidationError(
                f"Anthropic tool_use output did not match {response_model.__name__}: {exc}"
            ) from exc

    async def generate_with_tools(
        self,
        system_prompt: str,
        history: list[ConversationTurn],
        tools: list[ToolSpec],
        response_model: type[ResponseModel],
    ) -> AgentLLMResponse[ResponseModel]:
        import anthropic

        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ] + [
            {
                "name": _FINAL_ANSWER_TOOL_NAME,
                "description": _FINAL_ANSWER_TOOL_DESCRIPTION,
                "input_schema": response_model.model_json_schema(),
            }
        ]
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system_prompt,
                messages=_history_to_anthropic_messages(history),
                tools=anthropic_tools,
                tool_choice={"type": "auto"},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMAuthenticationError("Anthropic rejected the configured API key") from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError("Anthropic rate limit exceeded") from exc
        except anthropic.APITimeoutError as exc:
            raise LLMTimeoutError("Anthropic request timed out") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailableError("Could not connect to Anthropic") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailableError(f"Anthropic returned an error status: {exc.status_code}") from exc

        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if not tool_use_blocks:
            raise LLMResponseValidationError("Anthropic response contained no tool_use block")
        block = tool_use_blocks[0]

        if block.name == _FINAL_ANSWER_TOOL_NAME:
            try:
                final = response_model.model_validate(block.input)
            except ValidationError as exc:
                raise LLMResponseValidationError(
                    f"Anthropic final-answer output did not match {response_model.__name__}: {exc}"
                ) from exc
            return AgentLLMResponse(tool_call=None, final_answer=final)

        return AgentLLMResponse(
            tool_call=ToolCallRequest(call_id=block.id, tool_name=block.name, arguments=block.input),
            final_answer=None,
        )


def _history_to_anthropic_messages(history: list[ConversationTurn]) -> list[dict]:
    """Convert provider-agnostic ``ConversationTurn``s into Anthropic's
    message format. Turns always alternate user/assistant already (each
    ``tool_call`` -- assistant -- is immediately followed by exactly one
    ``tool_result`` -- user -- for it), so no merging is needed.
    """
    messages: list[dict] = []
    for turn in history:
        if turn.kind == "user":
            messages.append({"role": "user", "content": turn.content})
        elif turn.kind == "assistant_text":
            messages.append({"role": "assistant", "content": turn.content})
        elif turn.kind == "tool_call":
            assert turn.tool_call is not None
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": turn.tool_call.call_id,
                            "name": turn.tool_call.tool_name,
                            "input": turn.tool_call.arguments,
                        }
                    ],
                }
            )
        elif turn.kind == "tool_result":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": turn.call_id,
                            "content": json.dumps(turn.result),
                        }
                    ],
                }
            )
    return messages


class OpenAICompatibleProvider(LLMProvider):
    """Uses any OpenAI-compatible ``/chat/completions`` endpoint's JSON
    tool-calling support. No ``openai`` SDK dependency -- a plain HTTP
    POST via ``httpx`` (already a project dependency), which is all an
    OpenAI-compatible chat-completions call requires.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        # Test-only injection point: a real request never sets this, but
        # tests pass an httpx.MockTransport to exercise the real request/
        # response/error-mapping code below with zero network access.
        self._transport = transport

    async def generate_structured(
        self, system_prompt: str, input_data: dict, response_model: type[ResponseModel]
    ) -> ResponseModel:
        schema = response_model.model_json_schema()
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(input_data)},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": "Emit the structured explanation response.",
                        "parameters": schema,
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": _TOOL_NAME}},
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("OpenAI-compatible request timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMUnavailableError("Could not connect to the configured LLM_BASE_URL") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"OpenAI-compatible request failed: {exc}") from exc

        if response.status_code == 401:
            raise LLMAuthenticationError("Provider rejected the configured API key")
        if response.status_code == 429:
            raise LLMRateLimitError("Provider rate limit exceeded")
        if response.status_code >= 400:
            raise LLMUnavailableError(f"Provider returned status {response.status_code}")

        try:
            data = response.json()
            tool_calls = data["choices"][0]["message"]["tool_calls"]
            arguments = json.loads(tool_calls[0]["function"]["arguments"])
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMResponseValidationError(
                f"Provider response did not contain a usable tool call: {exc}"
            ) from exc

        try:
            return response_model.model_validate(arguments)
        except ValidationError as exc:
            raise LLMResponseValidationError(
                f"Provider tool call output did not match {response_model.__name__}: {exc}"
            ) from exc

    async def generate_with_tools(
        self,
        system_prompt: str,
        history: list[ConversationTurn],
        tools: list[ToolSpec],
        response_model: type[ResponseModel],
    ) -> AgentLLMResponse[ResponseModel]:
        function_tools = [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in tools
        ] + [
            {
                "type": "function",
                "function": {
                    "name": _FINAL_ANSWER_TOOL_NAME,
                    "description": _FINAL_ANSWER_TOOL_DESCRIPTION,
                    "parameters": response_model.model_json_schema(),
                },
            }
        ]
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": system_prompt}]
            + _history_to_openai_messages(history),
            "tools": function_tools,
            "tool_choice": "auto",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("OpenAI-compatible request timed out") from exc
        except httpx.ConnectError as exc:
            raise LLMUnavailableError("Could not connect to the configured LLM_BASE_URL") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"OpenAI-compatible request failed: {exc}") from exc

        if response.status_code == 401:
            raise LLMAuthenticationError("Provider rejected the configured API key")
        if response.status_code == 429:
            raise LLMRateLimitError("Provider rate limit exceeded")
        if response.status_code >= 400:
            raise LLMUnavailableError(f"Provider returned status {response.status_code}")

        try:
            data = response.json()
            tool_call = data["choices"][0]["message"]["tool_calls"][0]
            name = tool_call["function"]["name"]
            call_id = tool_call["id"]
            arguments = json.loads(tool_call["function"]["arguments"])
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMResponseValidationError(
                f"Provider response did not contain a usable tool call: {exc}"
            ) from exc

        if name == _FINAL_ANSWER_TOOL_NAME:
            try:
                final = response_model.model_validate(arguments)
            except ValidationError as exc:
                raise LLMResponseValidationError(
                    f"Provider final-answer output did not match {response_model.__name__}: {exc}"
                ) from exc
            return AgentLLMResponse(tool_call=None, final_answer=final)

        return AgentLLMResponse(
            tool_call=ToolCallRequest(call_id=call_id, tool_name=name, arguments=arguments),
            final_answer=None,
        )


def _history_to_openai_messages(history: list[ConversationTurn]) -> list[dict]:
    """Convert provider-agnostic ``ConversationTurn``s into OpenAI-style
    chat-completion messages (assistant tool_calls + role="tool" results).
    """
    messages: list[dict] = []
    for turn in history:
        if turn.kind == "user":
            messages.append({"role": "user", "content": turn.content})
        elif turn.kind == "assistant_text":
            messages.append({"role": "assistant", "content": turn.content})
        elif turn.kind == "tool_call":
            assert turn.tool_call is not None
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": turn.tool_call.call_id,
                            "type": "function",
                            "function": {
                                "name": turn.tool_call.tool_name,
                                "arguments": json.dumps(turn.tool_call.arguments),
                            },
                        }
                    ],
                }
            )
        elif turn.kind == "tool_result":
            messages.append(
                {"role": "tool", "tool_call_id": turn.call_id, "content": json.dumps(turn.result)}
            )
    return messages


class FakeLLMProvider(LLMProvider):
    """Deterministic, offline provider -- no API key, no network call.

    Used by the entire test suite, and selectable via ``LLM_PROVIDER=fake``
    for local development or CI/Docker verification when no real API key
    is configured (see docs/llm.md).

    By default, generates a safe, honest, always-valid response derived
    directly from ``input_data`` (see ``_default_response``). Tests that
    need to simulate a misbehaving or unavailable provider pass
    ``fixed_response`` (to return a specific, possibly hallucinating,
    payload) or ``raise_error`` (to simulate a provider failure) to the
    constructor.
    """

    def __init__(
        self,
        fixed_response: BaseModel | None = None,
        raise_error: LLMProviderError | None = None,
        agent_script: list[AgentLLMResponse] | None = None,
    ) -> None:
        self._fixed_response = fixed_response
        self._raise_error = raise_error
        # A pre-programmed sequence of ``AgentLLMResponse`` steps returned
        # in order, one per ``generate_with_tools`` call -- gives tests
        # exact, deterministic control over a full agent scenario (which
        # tool(s) get "requested", in what order, and the final answer)
        # without any text-guessing. See ``docs/agent.md``.
        self._agent_script = agent_script
        self._agent_call_index = 0

    async def generate_structured(
        self, system_prompt: str, input_data: dict, response_model: type[ResponseModel]
    ) -> ResponseModel:
        if self._raise_error is not None:
            raise self._raise_error
        if self._fixed_response is not None:
            return self._fixed_response  # type: ignore[return-value]
        return self._default_response(input_data, response_model)

    async def generate_with_tools(
        self,
        system_prompt: str,
        history: list[ConversationTurn],
        tools: list[ToolSpec],
        response_model: type[ResponseModel],
    ) -> AgentLLMResponse[ResponseModel]:
        if self._raise_error is not None:
            raise self._raise_error

        if self._agent_script is not None:
            if self._agent_call_index >= len(self._agent_script):
                raise LLMResponseValidationError(
                    "FakeLLMProvider.agent_script exhausted: the agent loop asked for "
                    f"a step beyond the {len(self._agent_script)} scripted (call index "
                    f"{self._agent_call_index}) -- the script doesn't cover this scenario."
                )
            step = self._agent_script[self._agent_call_index]
            self._agent_call_index += 1
            return step

        return self._default_agent_response(history, tools, response_model)

    def _default_agent_response(
        self,
        history: list[ConversationTurn],
        tools: list[ToolSpec],
        response_model: type[ResponseModel],
    ) -> AgentLLMResponse[ResponseModel]:
        """No script: a small, honest default so ``LLM_PROVIDER=fake``
        demonstrates real tool-calling (not just a static placeholder)
        without an API key. Reuses the exact same known-ingredient scan
        the anti-hallucination validator uses (``app.llm.validation
        .mentioned_known_ingredients``) against the user's own message --
        it can only ever call a tool with ingredient names the user
        actually typed, never a guessed or invented one. Real,
        precisely-scripted scenarios (tests) use ``agent_script`` instead.
        """
        from app.llm.validation import mentioned_known_ingredients

        tool_result_turns = [t for t in history if t.kind == "tool_result"]
        tool_names = {t.name for t in tools}

        if not tool_result_turns:
            user_turns = [t for t in history if t.kind == "user"]
            message_text = user_turns[-1].content if user_turns else ""
            mentioned = sorted(mentioned_known_ingredients(message_text or ""))

            if len(mentioned) >= 2 and "check_ingredient_compatibility" in tool_names:
                return AgentLLMResponse(
                    tool_call=ToolCallRequest(
                        call_id=f"fake-{len(history)}",
                        tool_name="check_ingredient_compatibility",
                        arguments={"ingredients": mentioned},
                    ),
                    final_answer=None,
                )
            if len(mentioned) == 1 and "get_ingredient_information" in tool_names:
                return AgentLLMResponse(
                    tool_call=ToolCallRequest(
                        call_id=f"fake-{len(history)}",
                        tool_name="get_ingredient_information",
                        arguments={"ingredient": mentioned[0]},
                    ),
                    final_answer=None,
                )

            final = response_model.model_validate(
                {
                    "answer": (
                        "I couldn't recognize a specific ingredient name in your message, so "
                        "I have nothing to check yet. Try naming one or two ingredients, or use "
                        "the dedicated Ingredient Analysis, Compare, or Routine pages directly."
                    ),
                    "key_points": [],
                    "limitations": [],
                }
            )
            return AgentLLMResponse(tool_call=None, final_answer=final)

        # At least one tool already ran: summarize what it found, using
        # only facts present in the tool result(s) themselves.
        sentences: list[str] = []
        for turn in tool_result_turns:
            result = turn.result if isinstance(turn.result, dict) else {}
            interactions = result.get("interactions")
            if isinstance(interactions, list):
                for item in interactions:
                    if isinstance(item, dict) and "ingredient_a" in item:
                        a = str(item["ingredient_a"]).replace("_", " ")
                        b = str(item["ingredient_b"]).replace("_", " ")
                        sentences.append(f"{a} and {b} have a documented {item['severity']}-level interaction.")
            if result.get("matched") is True and isinstance(result.get("normalized_name"), str):
                sentences.append(f"{result['normalized_name'].replace('_', ' ')} is a recognized ingredient.")
            elif result.get("matched") is False:
                sentences.append("That ingredient was not recognized in this system's rule set.")

        if not sentences:
            sentences.append("No documented interactions were found in this system's rule set.")

        final = response_model.model_validate(
            {"answer": " ".join(sentences), "key_points": [], "limitations": []}
        )
        return AgentLLMResponse(tool_call=None, final_answer=final)

    def _default_response(self, input_data: dict, response_model: type[ResponseModel]) -> ResponseModel:
        interactions = input_data.get("interactions", [])
        overlaps = input_data.get("overlapping_actives", [])
        unknowns = input_data.get("unknown_ingredients", []) or input_data.get(
            "unknown_ingredients_a", []
        )

        key_points: list[str] = []
        if interactions:
            key_points.append(f"{len(interactions)} documented ingredient interaction(s) were found.")
        if overlaps:
            key_points.append(f"{len(overlaps)} active ingredient(s) appear in more than one product.")
        if unknowns:
            key_points.append(f"{len(unknowns)} ingredient(s) were not recognized by this system.")
        if not key_points:
            key_points.append("No documented interactions or overlaps were found in this system's rule set.")

        summary = "This is a deterministic, rule-based summary: " + " ".join(key_points)

        interactions_explained = [
            {
                "rule_id": item["rule_id"],
                "explanation": (
                    f"A documented interaction was found between {item['ingredient_a']} and "
                    f"{item['ingredient_b']}."
                ),
            }
            for item in interactions
            if item.get("rule_id")
        ]
        overlap_explained = [
            {
                "ingredient": item["ingredient"],
                "explanation": f"{item['ingredient']} appears in {item['count']} of the products analyzed.",
            }
            for item in overlaps
        ]

        data = {
            "summary": summary,
            "key_points": key_points,
            "interactions_explained": interactions_explained,
            "overlap_explained": overlap_explained,
            "routine_notes": [],
        }
        return response_model.model_validate(data)


def get_llm_provider(settings: Settings) -> LLMProvider:
    """Select and construct the configured provider.

    Never raises: a configuration problem (missing key, unsupported
    provider name) is deferred to a ``FakeLLMProvider(raise_error=...)``
    that raises the appropriate ``LLMProviderError`` the moment
    ``generate_structured`` is actually called. This keeps "the provider
    is unusable" and "the provider call failed" the exact same code path
    for callers (see ``app.services.explanation_service``) -- constructing
    a provider is never itself a place a request can crash.
    """
    provider_name = settings.llm_provider.lower()

    if provider_name == "fake":
        return FakeLLMProvider()

    if provider_name == "anthropic":
        if not settings.llm_api_key:
            return FakeLLMProvider(
                raise_error=LLMAuthenticationError(
                    "LLM_API_KEY is not configured for provider 'anthropic'"
                )
            )
        return AnthropicProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    if provider_name == "openai":
        if not settings.llm_api_key:
            return FakeLLMProvider(
                raise_error=LLMAuthenticationError(
                    "LLM_API_KEY is not configured for provider 'openai'"
                )
            )
        base_url = settings.llm_base_url or "https://api.openai.com/v1"
        return OpenAICompatibleProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    return FakeLLMProvider(
        raise_error=LLMProviderError(f"Unsupported LLM_PROVIDER: {settings.llm_provider!r}")
    )
