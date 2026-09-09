"""Runs the LLM explanation-layer evaluation suite as a regular pytest
test. Fully offline: FakeLLMProvider only, no network, no API key.

Each test calls ``llm_runner.run()`` directly rather than sharing a
fixture -- every case here is a fast, local FakeLLMProvider call, so the
small re-run cost per test is worth avoiding any pytest-asyncio
fixture-scope mismatch with this project's function-scoped event loop
default (``asyncio_default_fixture_loop_scope = function`` in pytest.ini).
"""
from __future__ import annotations

import pytest

from evaluation.runners import llm_runner
from tests.evaluation._helpers import assert_all_passed

pytestmark = pytest.mark.asyncio


async def test_llm_evaluation_suite_passes() -> None:
    results = await llm_runner.run()
    assert_all_passed(results)


async def test_llm_evaluation_has_no_duplicate_case_ids() -> None:
    results = await llm_runner.run()
    ids = [r.case_id for r in results]
    assert len(ids) == len(set(ids))


async def test_llm_evaluation_covers_every_required_adversarial_case() -> None:
    results = await llm_runner.run()
    ids = {r.case_id for r in results}
    assert any("unsupported_ingredient" in c for c in ids)
    assert any("citation" in c for c in ids)
    assert any("numeric" in c for c in ids)
    assert any("diagnostic" in c for c in ids)
    assert any("url" in c for c in ids)
    assert any("provider_unavailable" in c for c in ids)


async def test_llm_evaluation_never_withholds_the_deterministic_analysis() -> None:
    """Every case's actual result must show the deterministic analysis
    was present, whether or not the explanation itself was accepted --
    this is the Phase 6 contract this evaluation exists to protect.
    """
    results = await llm_runner.run()
    for r in results:
        assert "the deterministic analysis was withheld" not in r.message
