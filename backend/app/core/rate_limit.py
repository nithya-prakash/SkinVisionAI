"""Minimal in-memory per-client rate limiting (Phase 12 follow-up).

Two endpoints carry a real per-request cost that a client could
otherwise hammer without limit: uploading an image (CPU: the quality
gate + vision pipeline) and the LLM-backed agent chat (real provider
token cost) -- rate-limited independently of authentication, as
defense-in-depth. A third, added alongside authentication itself
(release-hardening follow-up): login/register, to bound brute-force
password-guessing attempts. This module exists to bound those, not to
be a general-purpose API gateway.

Hand-rolled rather than adding a dependency (``slowapi``/``limits``) or
Redis: consistent with this project's existing preference for small,
auditable, dependency-free code (the agent loop and the anti-
hallucination validators are hand-rolled for the same reason), and with
the explicit choice not to add Redis for a single-process portfolio
deployment (see docker-compose.yml -- one ``api`` process, no worker
pool).

**Scope, stated honestly:** a fixed-window counter held in a process-
local dict, keyed by the connecting IP address.

- Fixed-window (not sliding-window/token-bucket) means a client can send
  up to ``2x`` the configured limit across a window boundary (e.g. the
  limit's worth of requests right at the end of one window, then again
  right at the start of the next). Accepted as a reasonable simplification
  for a portfolio-scale limiter, not a claim of precise, tunable traffic
  shaping.
- Process-local state means this is **not** correct for a multi-worker
  or multi-instance deployment -- each process would enforce its own
  independent limit. Fine for this project's single-process deployment;
  a real multi-instance deployment would need a shared store (Redis,
  the very thing deliberately not added here).
- Keyed by ``request.client.host`` only -- **not** ``X-Forwarded-For``-
  aware, since this project's `docker-compose.yml` has no reverse proxy
  in front of the API. Behind one, every client would share one IP (the
  proxy's) and this would under-limit; that's a disclosed limitation of
  this deployment shape, not an oversight.
"""
from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request

from app.config import Settings, get_settings


class _FixedWindowLimiter:
    """One independent counter per (limiter instance, client key)."""

    def __init__(self) -> None:
        # client_key -> (window_start, count_in_window). Plain dict, not
        # thread-safe by construction -- correct here because FastAPI/
        # uvicorn runs this as async code on a single event loop, and
        # nothing below awaits between reading and writing an entry, so
        # no other request can interleave mid-check.
        self._windows: dict[str, tuple[float, int]] = {}

    def check(self, key: str, max_requests: int, window_seconds: float) -> None:
        """Raise ``HTTPException(429)`` if ``key`` has already made
        ``max_requests`` requests within the current ``window_seconds``
        window; otherwise record this request and return normally.
        """
        now = time.monotonic()
        window_start, count = self._windows.get(key, (now, 0))

        if now - window_start >= window_seconds:
            # The previous window (if any) has elapsed -- start a fresh one.
            self._windows[key] = (now, 1)
            return

        if count >= max_requests:
            retry_after = max(1, round(window_seconds - (now - window_start)))
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "rate_limited",
                    "message": (
                        f"Too many requests. Please try again in about {retry_after} seconds."
                    ),
                },
                headers={"Retry-After": str(retry_after)},
            )

        self._windows[key] = (window_start, count + 1)


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


# One limiter instance per protected endpoint (not shared) -- an
# upload-heavy client and a chat-heavy client are throttled independently,
# each against its own endpoint's configured limit.
_upload_limiter = _FixedWindowLimiter()
_agent_chat_limiter = _FixedWindowLimiter()
_auth_limiter = _FixedWindowLimiter()


def rate_limit_upload(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """FastAPI dependency: ``Depends(rate_limit_upload)`` on a route."""
    _upload_limiter.check(
        _client_key(request),
        settings.rate_limit_upload_max_requests,
        settings.rate_limit_upload_window_seconds,
    )


def rate_limit_agent_chat(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """FastAPI dependency: ``Depends(rate_limit_agent_chat)`` on a route."""
    _agent_chat_limiter.check(
        _client_key(request),
        settings.rate_limit_agent_chat_max_requests,
        settings.rate_limit_agent_chat_window_seconds,
    )


def rate_limit_auth(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """FastAPI dependency: ``Depends(rate_limit_auth)`` on login/register."""
    _auth_limiter.check(
        _client_key(request),
        settings.rate_limit_auth_max_requests,
        settings.rate_limit_auth_window_seconds,
    )
