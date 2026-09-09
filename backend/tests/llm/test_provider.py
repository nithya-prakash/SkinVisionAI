"""Tests for app.llm.provider: FakeLLMProvider, the provider factory, and
real error-mapping in AnthropicProvider/OpenAICompatibleProvider.

No network access anywhere -- AnthropicProvider is tested by monkeypatching
its SDK client method directly; OpenAICompatibleProvider is tested with
httpx.MockTransport (no real HTTP connection is made).
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.config import Settings
from app.llm.base import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseValidationError,
    LLMTimeoutError,
    LLMUnavailableError,
    ToolSpec,
)
from app.llm.provider import (
    AnthropicProvider,
    FakeLLMProvider,
    OpenAICompatibleProvider,
    get_llm_provider,
)
from app.llm.schemas import ExplanationLLMOutput


# --- FakeLLMProvider ---


async def test_fake_provider_default_response_is_valid_and_honest() -> None:
    provider = FakeLLMProvider()
    input_data = {
        "interactions": [
            {"rule_id": "x", "ingredient_a": "a", "ingredient_b": "b", "severity": "caution"}
        ],
        "overlapping_actives": [],
    }
    result = await provider.generate_structured("system prompt", input_data, ExplanationLLMOutput)
    assert isinstance(result, ExplanationLLMOutput)
    assert "safe" not in result.summary.lower()
    assert len(result.interactions_explained) == 1
    assert result.interactions_explained[0].rule_id == "x"


async def test_fake_provider_default_response_with_no_findings() -> None:
    provider = FakeLLMProvider()
    result = await provider.generate_structured("p", {}, ExplanationLLMOutput)
    assert "no documented interactions" in result.summary.lower() or "no documented" in " ".join(
        result.key_points
    ).lower()


async def test_fake_provider_is_deterministic() -> None:
    provider = FakeLLMProvider()
    input_data = {"interactions": [], "overlapping_actives": []}
    first = await provider.generate_structured("p", input_data, ExplanationLLMOutput)
    second = await provider.generate_structured("p", input_data, ExplanationLLMOutput)
    assert first.model_dump() == second.model_dump()


async def test_fake_provider_fixed_response_override() -> None:
    fixed = ExplanationLLMOutput(summary="Custom fixed response.")
    provider = FakeLLMProvider(fixed_response=fixed)
    result = await provider.generate_structured("p", {}, ExplanationLLMOutput)
    assert result is fixed


async def test_fake_provider_raise_error() -> None:
    provider = FakeLLMProvider(raise_error=LLMTimeoutError("simulated timeout"))
    with pytest.raises(LLMTimeoutError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


# --- get_llm_provider factory ---


def test_get_llm_provider_fake() -> None:
    settings = Settings(llm_provider="fake")
    provider = get_llm_provider(settings)
    assert isinstance(provider, FakeLLMProvider)


def test_get_llm_provider_anthropic_with_key() -> None:
    settings = Settings(llm_provider="anthropic", llm_api_key="sk-test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, AnthropicProvider)


async def test_get_llm_provider_anthropic_missing_key_defers_error_to_call_time() -> None:
    settings = Settings(llm_provider="anthropic", llm_api_key=None)
    provider = get_llm_provider(settings)  # must not raise here
    assert isinstance(provider, FakeLLMProvider)
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_get_llm_provider_openai_missing_key_defers_error_to_call_time() -> None:
    settings = Settings(llm_provider="openai", llm_api_key=None)
    provider = get_llm_provider(settings)
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


def test_get_llm_provider_openai_with_key() -> None:
    settings = Settings(llm_provider="openai", llm_api_key="sk-test-key")
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAICompatibleProvider)


async def test_get_llm_provider_unsupported_name_defers_error_to_call_time() -> None:
    settings = Settings(llm_provider="totally-unsupported-vendor")
    provider = get_llm_provider(settings)
    with pytest.raises(LLMProviderError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


# --- AnthropicProvider error mapping (mocked SDK client, no network) ---


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code, request=request, json={"error": "simulated"})


async def test_anthropic_provider_maps_authentication_error() -> None:
    import anthropic

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    response = _http_response(401)
    provider._client.messages.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=anthropic.AuthenticationError("bad key", response=response, body=None)
    )
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_anthropic_provider_maps_rate_limit_error() -> None:
    import anthropic

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    response = _http_response(429)
    provider._client.messages.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=anthropic.RateLimitError("rate limited", response=response, body=None)
    )
    with pytest.raises(LLMRateLimitError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_anthropic_provider_maps_timeout_error() -> None:
    import anthropic

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    provider._client.messages.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=anthropic.APITimeoutError(request=request)
    )
    with pytest.raises(LLMTimeoutError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_anthropic_provider_maps_connection_error() -> None:
    import anthropic

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    provider._client.messages.create = AsyncMock(  # type: ignore[method-assign]
        side_effect=anthropic.APIConnectionError(request=request)
    )
    with pytest.raises(LLMUnavailableError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_anthropic_provider_raises_validation_error_on_no_tool_use() -> None:
    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")

    class _FakeResponse:
        content: list = []

    provider._client.messages.create = AsyncMock(return_value=_FakeResponse())  # type: ignore[method-assign]
    with pytest.raises(LLMResponseValidationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_anthropic_provider_generate_with_tools_rejects_malformed_final_answer() -> None:
    """Phase 10: the Phase 6 malformed-response coverage above exercises
    ``generate_structured`` only -- this is the equivalent case for
    ``generate_with_tools`` (Phase 7's agent path), which has its own
    separate ``response_model.model_validate`` call (provider.py) that was
    previously untested.
    """
    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")

    class _FinalAnswerBlock:
        type = "tool_use"
        id = "call-1"
        name = "provide_final_answer"
        # Missing the required "answer" field -- must fail schema validation.
        input = {"key_points": [], "limitations": []}

    class _FakeResponse:
        content = [_FinalAnswerBlock()]

    provider._client.messages.create = AsyncMock(return_value=_FakeResponse())  # type: ignore[method-assign]
    with pytest.raises(LLMResponseValidationError):
        await provider.generate_with_tools(
            system_prompt="p", history=[], tools=[], response_model=AgentFinalAnswerLLMOutput
        )


async def test_anthropic_provider_parses_valid_tool_use_response() -> None:
    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")

    class _ToolUseBlock:
        type = "tool_use"
        input = {"summary": "A valid summary from the model."}

    class _FakeResponse:
        content = [_ToolUseBlock()]

    provider._client.messages.create = AsyncMock(return_value=_FakeResponse())  # type: ignore[method-assign]
    result = await provider.generate_structured("p", {}, ExplanationLLMOutput)
    assert result.summary == "A valid summary from the model."


# --- OpenAICompatibleProvider error mapping (httpx.MockTransport, no network) ---


def _provider_with_handler(handler) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key="sk-test",
        model="test-model",
        base_url="https://example.invalid/v1",
        transport=httpx.MockTransport(handler),
    )


async def test_openai_provider_maps_401() -> None:
    provider = _provider_with_handler(lambda req: httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(LLMAuthenticationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_maps_429() -> None:
    provider = _provider_with_handler(lambda req: httpx.Response(429, json={"error": "rate limited"}))
    with pytest.raises(LLMRateLimitError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_maps_5xx() -> None:
    provider = _provider_with_handler(lambda req: httpx.Response(500, json={"error": "server error"}))
    with pytest.raises(LLMUnavailableError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_maps_malformed_response() -> None:
    provider = _provider_with_handler(lambda req: httpx.Response(200, json={"unexpected": "shape"}))
    with pytest.raises(LLMResponseValidationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_maps_schema_invalid_tool_arguments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [{"function": {"arguments": '{"summary": ""}'}}]
                        }
                    }
                ]
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMResponseValidationError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_generate_with_tools_rejects_malformed_final_answer() -> None:
    """Phase 10: the equivalent of
    ``test_openai_provider_maps_schema_invalid_tool_arguments`` above, but
    for ``generate_with_tools`` (Phase 7's agent path) rather than
    ``generate_structured`` (Phase 6) -- previously untested.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "provide_final_answer",
                                        # Missing the required "answer" field.
                                        "arguments": '{"key_points": [], "limitations": []}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMResponseValidationError):
        await provider.generate_with_tools(
            system_prompt="p", history=[], tools=[], response_model=AgentFinalAnswerLLMOutput
        )


async def test_openai_provider_parses_valid_success_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "arguments": '{"summary": "Explained via OpenAI-compatible provider."}'
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    provider = _provider_with_handler(handler)
    result = await provider.generate_structured("p", {}, ExplanationLLMOutput)
    assert result.summary == "Explained via OpenAI-compatible provider."


async def test_openai_provider_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMTimeoutError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)


async def test_openai_provider_maps_connect_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated connection failure", request=request)

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMUnavailableError):
        await provider.generate_structured("p", {}, ExplanationLLMOutput)
