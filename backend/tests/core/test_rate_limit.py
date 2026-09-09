"""Tests for app.core.rate_limit -- the hand-rolled fixed-window
per-client limiter (Phase 12 follow-up).

Unit-level: exercises ``_FixedWindowLimiter`` directly, not through the
ASGI app, so these run instantly and don't depend on real wall-clock
delays for the "under the limit" and "at the limit" cases. The window-
reset case does sleep briefly (a fixed-window limiter's reset is
inherently time-based) but only for a few hundred milliseconds.
"""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from app.core.rate_limit import _FixedWindowLimiter


def test_requests_under_the_limit_are_allowed() -> None:
    limiter = _FixedWindowLimiter()
    for _ in range(5):
        limiter.check("client-a", max_requests=5, window_seconds=60.0)  # must not raise


def test_the_request_that_exceeds_the_limit_is_rejected() -> None:
    limiter = _FixedWindowLimiter()
    for _ in range(3):
        limiter.check("client-a", max_requests=3, window_seconds=60.0)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("client-a", max_requests=3, window_seconds=60.0)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "rate_limited"
    assert "Retry-After" in exc_info.value.headers


def test_rejection_never_increments_the_counter_further() -> None:
    """Repeatedly hitting a rate-limited client keeps rejecting it --
    the count doesn't keep climbing past the limit forever, and a
    rejected request doesn't itself "use up" a slot in a future window.
    """
    limiter = _FixedWindowLimiter()
    limiter.check("client-a", max_requests=1, window_seconds=60.0)
    for _ in range(5):
        with pytest.raises(HTTPException):
            limiter.check("client-a", max_requests=1, window_seconds=60.0)


def test_different_clients_are_tracked_independently() -> None:
    limiter = _FixedWindowLimiter()
    limiter.check("client-a", max_requests=1, window_seconds=60.0)

    with pytest.raises(HTTPException):
        limiter.check("client-a", max_requests=1, window_seconds=60.0)

    limiter.check("client-b", max_requests=1, window_seconds=60.0)  # must not raise -- different key


def test_limit_resets_after_the_window_elapses() -> None:
    limiter = _FixedWindowLimiter()
    limiter.check("client-a", max_requests=1, window_seconds=0.2)

    with pytest.raises(HTTPException):
        limiter.check("client-a", max_requests=1, window_seconds=0.2)

    time.sleep(0.25)
    limiter.check("client-a", max_requests=1, window_seconds=0.2)  # must not raise -- new window


def test_retry_after_header_is_a_positive_integer_within_the_window() -> None:
    limiter = _FixedWindowLimiter()
    limiter.check("client-a", max_requests=1, window_seconds=30.0)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("client-a", max_requests=1, window_seconds=30.0)

    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 30


def test_error_message_never_contains_the_client_key() -> None:
    """The client key (an IP address) must never be echoed back into the
    response body -- it's only ever used internally to bucket requests.
    """
    limiter = _FixedWindowLimiter()
    limiter.check("203.0.113.42", max_requests=1, window_seconds=60.0)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("203.0.113.42", max_requests=1, window_seconds=60.0)

    assert "203.0.113.42" not in exc_info.value.detail["message"]
