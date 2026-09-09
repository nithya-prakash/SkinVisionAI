"""Phase 10: the global exception handler (app/main.py) and the
decompression-bomb upload guard (app/core/upload_validation.py).

Verifies the actual, deployed behavior rather than trusting the code's
own doc comments: an unhandled exception must return a sanitized,
generic response (never a traceback/path/internal detail), while an
already-controlled ``HTTPException`` (a 404, a 422, a domain-specific
4xx) must be completely unaffected by the new catch-all handler.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app


async def _raise_runtime_error() -> AsyncSession:
    raise RuntimeError("simulated unexpected internal failure: /etc/shadow secret-db-password")
    yield  # pragma: no cover -- unreachable, keeps this a valid async generator


@pytest.mark.asyncio
async def test_unhandled_exception_returns_sanitized_500() -> None:
    # Starlette's ServerErrorMiddleware always re-raises the original
    # exception after sending the response, specifically so a real ASGI
    # server can still log it -- httpx's ASGITransport mirrors that by
    # default (raise_app_exceptions=True) for the same reason real
    # bugs surface loudly in tests. Here the re-raise-after-send *is*
    # the exact behavior under test (the response was already sent
    # sanitized before the re-raise), so this one test builds its own
    # client with raise_app_exceptions=False to observe that response
    # instead of the exception -- the shared `client` fixture keeps its
    # default (safer for every other test, which should fail loudly on
    # a genuine bug rather than silently returning a 500).
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    app.dependency_overrides[get_db] = _raise_runtime_error
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/sessions/{uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "detail": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    # Never leaks the actual exception text, a path, or any secret-looking
    # substring that was in it.
    assert "RuntimeError" not in response.text
    assert "/etc/shadow" not in response.text
    assert "secret-db-password" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_controlled_404_unaffected_by_global_handler(client: AsyncClient) -> None:
    response = await client.get(f"/api/sessions/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


@pytest.mark.asyncio
async def test_malformed_uuid_path_param_returns_clean_422(client: AsyncClient) -> None:
    response = await client.get("/api/analysis/not-a-uuid")
    assert response.status_code == 422
    # FastAPI/Pydantic's own coercion error -- no traceback, no path.
    assert "Traceback" not in response.text
    assert "/app/" not in response.text


@pytest.mark.asyncio
async def test_analysis_not_found_unaffected_by_global_handler(client: AsyncClient) -> None:
    response = await client.get(f"/api/analysis/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_not_found"
