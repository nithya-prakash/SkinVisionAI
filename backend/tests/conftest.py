"""Shared pytest fixtures.

API-level tests in this suite talk to a real PostgreSQL database (via
``DATABASE_URL``) rather than mocking the ORM -- consistent with this
project's convention of verifying database-touching code against real
infrastructure. Run them with a Postgres instance reachable at the
configured URL (see ``docker-compose.yml`` / README setup instructions).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core.rate_limit import _agent_chat_limiter, _auth_limiter, _upload_limiter
from app.main import app


@pytest.fixture(autouse=True)
def _reset_dependency_overrides() -> None:
    """Ensure no test leaks shared app-level state into the next one:
    a dependency override, a cached ``Settings`` instance, or -- since
    every test in this session shares one ASGI ``app`` and its
    process-local rate-limit counters (see app.core.rate_limit) -- an
    accumulated request count against the default rate limits. Without
    this, a test file with enough upload/chat/auth requests in one
    pytest session would start tripping the real default limits (10/min,
    20/min, 10/min) purely from test volume, unrelated to what any
    individual test is actually checking.
    """
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    _upload_limiter._windows.clear()
    _agent_chat_limiter._windows.clear()
    _auth_limiter._windows.clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """An unauthenticated client -- use for testing the auth endpoints
    themselves (register/login/me-while-signed-out) or a route's 401
    when no one is signed in. Every session-scoped route now requires
    authentication (release-hardening follow-up); use
    ``authenticated_client`` for those.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def authenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """A client already signed in as a fresh, throwaway test user (a
    unique email per fixture instance, so tests don't collide with each
    other in the shared test database -- see the module docstring).
    httpx's ``AsyncClient`` keeps a cookie jar automatically, so the
    ``Set-Cookie`` from ``/api/auth/register`` rides along on every
    subsequent request through this same client -- no manual header
    wiring needed, exactly how a real browser session behaves.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        email = f"test-{uuid.uuid4().hex}@example.com"
        response = await ac.post(
            "/api/auth/register", json={"email": email, "password": "testpassword123"}
        )
        assert response.status_code == 201, response.text
        yield ac
