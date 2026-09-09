"""Shared pytest fixtures.

API-level tests in this suite talk to a real PostgreSQL database (via
``DATABASE_URL``) rather than mocking the ORM -- consistent with this
project's convention of verifying database-touching code against real
infrastructure. Run them with a Postgres instance reachable at the
configured URL (see ``docker-compose.yml`` / README setup instructions).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.core.rate_limit import _agent_chat_limiter, _upload_limiter
from app.main import app


@pytest.fixture(autouse=True)
def _reset_dependency_overrides() -> None:
    """Ensure no test leaks shared app-level state into the next one:
    a dependency override, a cached ``Settings`` instance, or -- since
    every test in this session shares one ASGI ``app`` and its
    process-local rate-limit counters (see app.core.rate_limit) -- an
    accumulated request count against the default rate limits. Without
    this, a test file with enough upload/chat requests in one pytest
    session would start tripping the real default limits (10/min,
    20/min) purely from test volume, unrelated to what any individual
    test is actually checking.
    """
    yield
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    _upload_limiter._windows.clear()
    _agent_chat_limiter._windows.clear()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
