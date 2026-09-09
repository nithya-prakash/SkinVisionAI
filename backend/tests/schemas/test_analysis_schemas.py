"""Tests for app.schemas.analysis -- session/analysis identifiers and the
top-level analysis shape. Verifies Phase 1 never fabricates ML output and
always carries the safety disclaimer.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisStatus,
    SessionRead,
    SkinAnalysisCreate,
    SkinAnalysisRead,
)
from app.schemas.common import DISCLAIMER


def test_session_read_valid() -> None:
    session = SessionRead(id=uuid4(), created_at="2026-01-01T00:00:00Z")
    assert session.id is not None


def test_session_read_missing_created_at_raises() -> None:
    with pytest.raises(ValidationError):
        SessionRead(id=uuid4())


def test_skin_analysis_create_valid() -> None:
    payload = SkinAnalysisCreate(session_id=uuid4(), image_id=uuid4())
    assert payload.session_id is not None


def test_skin_analysis_read_defaults_to_no_observations() -> None:
    analysis = SkinAnalysisRead(
        id=uuid4(),
        session_id=uuid4(),
        image_id=uuid4(),
        status=AnalysisStatus.PENDING,
        created_at="2026-01-01T00:00:00Z",
    )
    assert analysis.visual_observations == []


def test_skin_analysis_read_always_carries_disclaimer() -> None:
    analysis = SkinAnalysisRead(
        id=uuid4(),
        session_id=uuid4(),
        image_id=uuid4(),
        status=AnalysisStatus.COMPLETED,
        created_at="2026-01-01T00:00:00Z",
    )
    assert analysis.disclaimer == DISCLAIMER
    assert "not medical diagnosis" in analysis.disclaimer


def test_skin_analysis_read_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        SkinAnalysisRead(
            id=uuid4(),
            session_id=uuid4(),
            image_id=uuid4(),
            status="diagnosed",
            created_at="2026-01-01T00:00:00Z",
        )


def test_skin_analysis_read_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SkinAnalysisRead(
            id=uuid4(),
            session_id=uuid4(),
            image_id=uuid4(),
            status=AnalysisStatus.PENDING,
            created_at="2026-01-01T00:00:00Z",
            diagnosis="acne",
        )
