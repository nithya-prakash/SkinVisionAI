"""End-to-end Phase 8 integration test.

Session -> upload synthetic image -> quality check -> visual analysis ->
create a chat session -> user question -> agent tool call -> deterministic
result -> LLM explanation -> validation -> persist message + trace ->
retrieve chat history -> retrieve analysis.

The LLM is faked (``FakeLLMProvider``, script-driven -- no API key, no
network); every deterministic engine (image quality, vision pipeline,
ingredient compatibility) is real. PostgreSQL is real, matching this
project's established convention of verifying database-touching code
against real infrastructure rather than mocking the ORM.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.agent.schemas import AgentFinalAnswerLLMOutput
from app.api.agent import _provider
from app.llm.base import AgentLLMResponse, ToolCallRequest
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


@pytest.mark.asyncio
async def test_full_session_upload_analysis_chat_lifecycle(client: AsyncClient) -> None:
    # 1. SESSION
    session = await client.post("/api/sessions")
    assert session.status_code == 201
    session_id = session.json()["id"]

    # 2. UPLOAD SYNTHETIC IMAGE (+ QUALITY CHECK, real engine)
    upload = await client.post(
        "/api/analysis/upload",
        files={
            "file": ("photo.jpg", to_bytes(make_acceptable_image(800, 800), "JPEG"), "image/jpeg")
        },
        data={"session_id": session_id},
    )
    assert upload.status_code == 201
    upload_body = upload.json()
    assert upload_body["quality"]["is_acceptable"] is True
    analysis_id = upload_body["analysis_id"]

    # Confirm retrievable pre-analysis state before running the pipeline.
    pre = await client.get(f"/api/analysis/{analysis_id}")
    assert pre.json()["status"] == "ready_for_visual_analysis"

    # 3. VISUAL ANALYSIS (real engine)
    visual = await client.post(f"/api/analysis/{analysis_id}/visual-analysis")
    assert visual.status_code == 200
    assert len(visual.json()["observations"]) == 5

    # Confirm the session's analysis list now reflects completion.
    analyses = await client.get(f"/api/sessions/{session_id}/analyses")
    assert analyses.json()["analyses"][0]["status"] == "completed"

    # 4. ANALYZE A PRODUCT (real deterministic engine), for the chat to reference
    product = await client.post(
        "/api/products/analyze",
        json={
            "session_id": session_id,
            "name": "Retinol Serum",
            "raw_ingredient_text": "Retinol, Glycolic Acid",
        },
    )
    assert product.status_code == 201
    product_id = product.json()["product_id"]
    assert product.json()["compatibility"]["interactions"][0]["severity"] == "caution"

    # 5. CREATE CHAT SESSION linked to that product + 6-9. USER QUESTION ->
    #    AGENT TOOL CALL -> DETERMINISTIC RESULT -> LLM EXPLANATION -> VALIDATION
    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        agent_script=[
            _final(
                "Retinol and glycolic acid have a documented caution-level interaction."
            )
        ]
    )
    try:
        chat = await client.post(
            "/api/agent/chat",
            json={
                "message": "Can I use this product's ingredients together?",
                "session_id": session_id,
                "link": {"product_id": product_id},
            },
        )
    finally:
        app.dependency_overrides.pop(_provider, None)

    assert chat.status_code == 200
    chat_body = chat.json()
    assert chat_body["status"] == "success"
    assert chat_body["tool_trace"][0]["tool_name"] == "linked_product_analysis"
    assert chat_body["tool_trace"][0]["success"] is True
    assert chat_body["citations"][0]["source"] == "Cleveland Clinic"
    chat_session_id = chat_body["chat_session_id"]

    # 10. PERSIST MESSAGE + TRACE happened as part of the call above --
    # verify by retrieving fresh from the database (a new request).
    # 11. RETRIEVE CHAT HISTORY
    history = await client.get(f"/api/chat/sessions/{chat_session_id}/messages")
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == chat_body["answer"]
    assert messages[1]["tool_trace"] == chat_body["tool_trace"]

    chat_session_row = await client.get(f"/api/chat/sessions/{chat_session_id}")
    assert chat_session_row.json()["product_id"] == product_id
    assert chat_session_row.json()["session_id"] == session_id

    # 12. RETRIEVE ANALYSIS (the visual analysis from step 3)
    final_analysis = await client.get(f"/api/analysis/{analysis_id}")
    assert final_analysis.status_code == 200
    assert final_analysis.json()["status"] == "completed"
    assert final_analysis.json()["visual_analysis"]["observations"] == visual.json()["observations"]

    # Session-level view ties everything together.
    chats = await client.get(f"/api/sessions/{session_id}/chats")
    assert chats.json()["chats"][0]["id"] == chat_session_id
    assert chats.json()["chats"][0]["message_count"] == 2


@pytest.mark.asyncio
async def test_multi_step_agent_reasoning_with_real_tool_calls_persists_full_trace(
    client: AsyncClient,
) -> None:
    """A second integration scenario: the agent calls a real (not linked)
    tool mid-conversation, demonstrating the full
    tool-call -> deterministic-result -> validated-explanation pipeline
    without any pre-existing linked context.
    """
    session_id = (await client.post("/api/sessions")).json()["id"]

    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        agent_script=[
            _call(
                "check_ingredient_compatibility",
                {"ingredients": ["retinol", "salicylic acid"]},
            ),
            _final("These have a documented caution-level interaction."),
        ]
    )
    try:
        chat = await client.post(
            "/api/agent/chat",
            json={
                "message": "Can I use retinol and salicylic acid together?",
                "session_id": session_id,
            },
        )
    finally:
        app.dependency_overrides.pop(_provider, None)

    assert chat.status_code == 200
    body = chat.json()
    assert body["tool_trace"][0]["tool_name"] == "check_ingredient_compatibility"
    assert body["tool_trace"][0]["result"]["interactions"][0]["severity"] == "caution"

    history = await client.get(f"/api/chat/sessions/{body['chat_session_id']}/messages")
    assert history.json()["messages"][-1]["tool_trace"][0]["tool_name"] == (
        "check_ingredient_compatibility"
    )
