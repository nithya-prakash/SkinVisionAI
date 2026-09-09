"""Integration tests for chat-history retrieval
(``GET /api/chat/sessions/{id}``, ``.../messages``) and the Phase 8
``AgentChatRequest.link`` feature.

Phase 7's own live-turn behavior (tool calls, hallucination rejection,
LLM failure, etc.) is already covered by ``tests/agent/test_agent_api.py``
-- this file covers what's new in Phase 8: reading a conversation back
after it was persisted, and linking a chat session to an existing
analysis/product/routine/comparison so the agent receives it as trusted
context without a real tool call.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.api.agent import _provider
from app.llm.base import AgentLLMResponse, LLMTimeoutError, ToolCallRequest
from app.llm.provider import FakeLLMProvider
from app.main import app
from tests.helpers.images import make_acceptable_image, to_bytes


def _final(answer: str) -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=None,
        final_answer=AgentFinalAnswerLLMOutput(answer=answer, key_points=[], limitations=[]),
    )


def _call(tool_name: str, arguments: dict, call_id: str = "call-1") -> AgentLLMResponse:
    return AgentLLMResponse(
        tool_call=ToolCallRequest(call_id=call_id, tool_name=tool_name, arguments=arguments),
        final_answer=None,
    )


def _use_script(script) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(agent_script=script)


@pytest.fixture(autouse=True)
def _default_fake_provider():
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(agent_script=[_final("ok")])
    yield
    app.dependency_overrides.pop(_provider, None)


# --- History retrieval ---


@pytest.mark.asyncio
async def test_get_chat_session_unknown_id_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/chat/sessions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "chat_session_not_found"


@pytest.mark.asyncio
async def test_list_chat_messages_unknown_id_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/chat/sessions/{uuid.uuid4()}/messages")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_then_retrieve_history(client: AsyncClient) -> None:
    _use_script([_final("Hi there!")])
    chat = await client.post("/api/agent/chat", json={"message": "Hello"})
    chat_session_id = chat.json()["chat_session_id"]

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    assert response.status_code == 200
    body = response.json()
    assert body["chat_session_id"] == chat_session_id
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "Hello"
    assert body["messages"][1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_persisted_messages_survive_across_requests(client: AsyncClient) -> None:
    """Simulates a page refresh: history is retrieved via a fresh request,
    not carried over from the one that created it.
    """
    _use_script([_final("First answer.")])
    first = await client.post("/api/agent/chat", json={"message": "First question"})
    chat_session_id = first.json()["chat_session_id"]

    # A brand-new request, as if the page had just reloaded.
    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    assert len(response.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_multi_turn_conversation_all_persisted(client: AsyncClient) -> None:
    _use_script([_final("Answer one.")])
    first = await client.post("/api/agent/chat", json={"message": "Question one"})
    chat_session_id = first.json()["chat_session_id"]

    _use_script([_final("Answer two.")])
    await client.post(
        "/api/agent/chat", json={"message": "Question two", "chat_session_id": chat_session_id}
    )

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    contents = [m["content"] for m in response.json()["messages"]]
    assert contents == ["Question one", "Answer one.", "Question two", "Answer two."]


@pytest.mark.asyncio
async def test_persisted_trace_reconstructed_on_retrieval(client: AsyncClient) -> None:
    _use_script(
        [
            _call("check_ingredient_compatibility", {"ingredients": ["retinol", "salicylic acid"]}),
            _final("These have a documented caution-level interaction."),
        ]
    )
    chat = await client.post(
        "/api/agent/chat", json={"message": "Can I combine retinol and salicylic acid?"}
    )
    chat_session_id = chat.json()["chat_session_id"]
    live_trace = chat.json()["tool_trace"]

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    assistant_message = response.json()["messages"][-1]
    assert assistant_message["tool_trace"] == live_trace
    assert assistant_message["tool_trace"][0]["tool_name"] == "check_ingredient_compatibility"
    assert assistant_message["tool_trace"][0]["success"] is True


@pytest.mark.asyncio
async def test_failed_tool_call_trace_also_persisted(client: AsyncClient) -> None:
    _use_script(
        [
            _call("execute_python", {"code": "..."}),
            _final("I can't run code, but I can check ingredient compatibility."),
        ]
    )
    chat = await client.post("/api/agent/chat", json={"message": "Run some code for me"})
    chat_session_id = chat.json()["chat_session_id"]

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    trace = response.json()["messages"][-1]["tool_trace"]
    assert trace[0]["success"] is False
    assert "unknown tool" in trace[0]["error"]


# --- ChatLink (Phase 8) ---


@pytest.mark.asyncio
async def test_link_to_product_injects_context_without_a_tool_call(client: AsyncClient) -> None:
    product = await client.post(
        "/api/products/analyze",
        json={"name": "Retinol Serum", "raw_ingredient_text": "Retinol"},
    )
    product_id = product.json()["product_id"]

    _use_script([_final("No documented interactions were found in this system's rule set.")])
    chat = await client.post(
        "/api/agent/chat",
        json={"message": "Tell me about this product", "link": {"product_id": product_id}},
    )
    assert chat.status_code == 200
    body = chat.json()
    assert body["tool_trace"][0]["tool_name"] == "linked_product_analysis"
    assert body["tool_trace"][0]["success"] is True

    session_row = await client.get(f"/api/chat/sessions/{body['chat_session_id']}")
    assert session_row.json()["product_id"] == product_id


@pytest.mark.asyncio
async def test_link_to_skin_analysis_injects_context(client: AsyncClient) -> None:
    upload = await client.post(
        "/api/analysis/upload",
        files={"file": ("photo.jpg", to_bytes(make_acceptable_image(800, 800), "JPEG"), "image/jpeg")},
    )
    analysis_id = upload.json()["analysis_id"]
    await client.post(f"/api/analysis/{analysis_id}/visual-analysis")

    _use_script([_final("Here is a summary of what was observed.")])
    chat = await client.post(
        "/api/agent/chat",
        json={"message": "What did you see?", "link": {"skin_analysis_id": analysis_id}},
    )
    assert chat.status_code == 200
    assert chat.json()["tool_trace"][0]["tool_name"] == "linked_skin_analysis"


@pytest.mark.asyncio
async def test_link_to_routine_analysis_record_injects_context(client: AsyncClient) -> None:
    routine = await client.post(
        "/api/routine/analyze",
        json={"persist": True, "products": [{"product_name": "A", "raw_ingredients": "Retinol"}]},
    )
    routine_id = routine.json()["id"]
    assert routine_id is not None

    _use_script([_final("Here is what your routine analysis found.")])
    chat = await client.post(
        "/api/agent/chat",
        json={"message": "Explain my routine", "link": {"routine_analysis_id": routine_id}},
    )
    assert chat.status_code == 200
    assert chat.json()["tool_trace"][0]["tool_name"] == "linked_routine_analysis"


@pytest.mark.asyncio
async def test_link_to_comparison_record_injects_context(client: AsyncClient) -> None:
    comparison = await client.post(
        "/api/products/compare",
        json={
            "persist": True,
            "product_a": {"name": "A", "raw_ingredient_text": "Retinol"},
            "product_b": {"name": "B", "raw_ingredient_text": "Niacinamide"},
        },
    )
    comparison_id = comparison.json()["id"]
    assert comparison_id is not None

    _use_script([_final("Here is how the two products compare.")])
    chat = await client.post(
        "/api/agent/chat",
        json={"message": "Compare these for me", "link": {"comparison_id": comparison_id}},
    )
    assert chat.status_code == 200
    assert chat.json()["tool_trace"][0]["tool_name"] == "linked_comparison"


@pytest.mark.asyncio
async def test_link_to_unknown_product_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/agent/chat",
        json={"message": "Hi", "link": {"product_id": str(uuid.uuid4())}},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_chat_link"


@pytest.mark.asyncio
async def test_link_requires_exactly_one_field_set(client: AsyncClient) -> None:
    response = await client.post(
        "/api/agent/chat",
        json={
            "message": "Hi",
            "link": {"product_id": str(uuid.uuid4()), "comparison_id": str(uuid.uuid4())},
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_link_ignored_when_continuing_an_existing_chat_session(client: AsyncClient) -> None:
    product = await client.post(
        "/api/products/analyze",
        json={"name": "A", "raw_ingredient_text": "Retinol"},
    )
    product_id = product.json()["product_id"]

    _use_script([_final("Hello.")])
    first = await client.post("/api/agent/chat", json={"message": "Hi"})
    chat_session_id = first.json()["chat_session_id"]

    # Continuing the same (unlinked) chat session with a `link` set must
    # not retroactively link it -- linkage is fixed at creation.
    _use_script([_final("No documented interactions were found in this system's rule set.")])
    second = await client.post(
        "/api/agent/chat",
        json={
            "message": "Follow-up",
            "chat_session_id": chat_session_id,
            "link": {"product_id": product_id},
        },
    )
    assert second.status_code == 200
    session_row = await client.get(f"/api/chat/sessions/{chat_session_id}")
    assert session_row.json()["product_id"] is None


# --- Controlled failure behavior (retrieval side) ---


@pytest.mark.asyncio
async def test_llm_failure_message_and_empty_trace_still_persisted_and_retrievable(
    client: AsyncClient,
) -> None:
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        raise_error=LLMTimeoutError("simulated")
    )
    chat = await client.post("/api/agent/chat", json={"message": "Hello"})
    assert chat.json()["status"] == "llm_unavailable"
    chat_session_id = chat.json()["chat_session_id"]

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    messages = response.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == ""


@pytest.mark.asyncio
async def test_validation_failure_persisted_with_empty_answer(client: AsyncClient) -> None:
    _use_script([_final("Retinol and niacinamide are completely safe together.")])
    chat = await client.post(
        "/api/agent/chat", json={"message": "Are retinol and niacinamide safe together?"}
    )
    assert chat.json()["status"] == "validation_error"
    chat_session_id = chat.json()["chat_session_id"]

    response = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    messages = response.json()["messages"]
    assert messages[1]["content"] == ""
