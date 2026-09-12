"""Integration tests for the authentication endpoints (release-hardening
follow-up): ``POST /api/auth/{register,login,logout}``,
``GET /api/auth/me``.

The most important tests here aren't about auth in isolation -- they're
the tests that prove the actual vulnerability this pass fixed
("anonymous session ID alone grants access") is closed: a second,
independently registered user cannot read or act on the first user's
session, chat, or analysis, even holding its exact UUID. See
docs/persistence.md's Security section for the before/after.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_register_creates_account_and_signs_in(client: AsyncClient) -> None:
    email = f"new-{uuid.uuid4().hex}@example.com"
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "testpassword123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert uuid.UUID(body["id"])
    assert uuid.UUID(body["session_id"])
    assert "hashed_password" not in body
    assert "password" not in body
    # The register call already signs the caller in -- no separate login
    # needed to use the cookie it set.
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == email


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    email = f"dup-{uuid.uuid4().hex}@example.com"
    first = await client.post(
        "/api/auth/register", json={"email": email, "password": "testpassword123"}
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/auth/register", json={"email": email, "password": "anotherpassword456"}
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "email_already_registered"


@pytest.mark.asyncio
async def test_register_rejects_a_too_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": f"weak-{uuid.uuid4().hex}@example.com", "password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_credentials(client: AsyncClient) -> None:
    email = f"login-{uuid.uuid4().hex}@example.com"
    await client.post("/api/auth/register", json={"email": email, "password": "testpassword123"})
    await client.post("/api/auth/logout")

    response = await client.post(
        "/api/auth/login", json={"email": email, "password": "testpassword123"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == email


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    email = f"wrongpw-{uuid.uuid4().hex}@example.com"
    await client.post("/api/auth/register", json={"email": email, "password": "testpassword123"})

    response = await client.post(
        "/api/auth/login", json={"email": email, "password": "not-the-right-password"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": f"never-registered-{uuid.uuid4().hex}@example.com", "password": "whatever123"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"


@pytest.mark.asyncio
async def test_logout_clears_the_session(authenticated_client: AsyncClient) -> None:
    still_in = await authenticated_client.get("/api/auth/me")
    assert still_in.status_code == 200

    logout = await authenticated_client.post("/api/auth/logout")
    assert logout.status_code == 204

    after = await authenticated_client.get("/api/auth/me")
    assert after.status_code == 401


async def _second_user_client() -> AsyncClient:
    """A second, independently authenticated client -- a different user
    than whatever ``authenticated_client`` fixture is in play, for the
    cross-user ownership tests below.
    """
    transport = ASGITransport(app=app)
    ac = AsyncClient(transport=transport, base_url="http://test")
    email = f"other-{uuid.uuid4().hex}@example.com"
    response = await ac.post(
        "/api/auth/register", json={"email": email, "password": "testpassword123"}
    )
    assert response.status_code == 201
    return ac


# --- The actual vulnerability fix: cross-user ownership enforcement ---


@pytest.mark.asyncio
async def test_a_user_cannot_read_another_users_session(authenticated_client: AsyncClient) -> None:
    my_session_id = (await authenticated_client.post("/api/sessions")).json()["id"]

    other = await _second_user_client()
    try:
        response = await other.get(f"/api/sessions/{my_session_id}")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "session_forbidden"
    finally:
        await other.aclose()


@pytest.mark.asyncio
async def test_a_user_cannot_list_another_users_analyses(authenticated_client: AsyncClient) -> None:
    my_session_id = (await authenticated_client.post("/api/sessions")).json()["id"]

    other = await _second_user_client()
    try:
        response = await other.get(f"/api/sessions/{my_session_id}/analyses")
        assert response.status_code == 403
    finally:
        await other.aclose()


@pytest.mark.asyncio
async def test_a_user_cannot_spend_another_users_session_id_on_a_write(
    authenticated_client: AsyncClient,
) -> None:
    """Naming someone else's real session_id on a write path (product
    analysis) is rejected, not silently redirected to a fresh session of
    the caller's own or, worse, honored as the named session.
    """
    my_session_id = (await authenticated_client.post("/api/sessions")).json()["id"]

    other = await _second_user_client()
    try:
        response = await other.post(
            "/api/products/analyze",
            json={
                "session_id": my_session_id,
                "name": "Someone Else's Product",
                "raw_ingredient_text": "Water",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "session_forbidden"
    finally:
        await other.aclose()


@pytest.mark.asyncio
async def test_a_user_cannot_continue_another_users_chat(authenticated_client: AsyncClient) -> None:
    from app.agent.schemas import AgentFinalAnswerLLMOutput
    from app.api.agent import _provider
    from app.llm.base import AgentLLMResponse
    from app.llm.provider import FakeLLMProvider

    app.dependency_overrides[_provider] = lambda: FakeLLMProvider(
        agent_script=[
            AgentLLMResponse(
                tool_call=None,
                final_answer=AgentFinalAnswerLLMOutput(answer="Hello!", key_points=[], limitations=[]),
            )
        ]
    )
    try:
        chat = await authenticated_client.post("/api/agent/chat", json={"message": "Hi"})
        assert chat.status_code == 200
        chat_session_id = chat.json()["chat_session_id"]

        other = await _second_user_client()
        try:
            hijack = await other.post(
                "/api/agent/chat",
                json={"message": "continue for me", "chat_session_id": chat_session_id},
            )
            assert hijack.status_code == 403
            assert hijack.json()["detail"]["code"] == "session_forbidden"

            history = await other.get(f"/api/chat/sessions/{chat_session_id}")
            assert history.status_code == 403

            messages = await other.get(f"/api/chat/sessions/{chat_session_id}/messages")
            assert messages.status_code == 403
        finally:
            await other.aclose()
    finally:
        app.dependency_overrides.pop(_provider, None)


@pytest.mark.asyncio
async def test_an_unknown_session_id_still_404s_for_an_authenticated_user(
    authenticated_client: AsyncClient,
) -> None:
    """A session id that was never actually created by anyone is a 404,
    not a 403 -- distinguishing "doesn't exist" from "exists but isn't
    yours" stays intact after adding auth.
    """
    response = await authenticated_client.get(f"/api/sessions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"
