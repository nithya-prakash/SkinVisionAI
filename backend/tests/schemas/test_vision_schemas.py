"""Tests for app.schemas.vision.

These schemas describe visible characteristics only -- never a diagnosis.
The tests below double as a guard: any attempt to smuggle a diagnostic
label through an unvalidated field should fail loudly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.vision import (
    ObservationFeature,
    ObservationLevel,
    RegionSource,
    VisualAnalysisResult,
    VisualObservation,
)


def test_visual_observation_valid() -> None:
    obs = VisualObservation(
        feature=ObservationFeature.REDNESS,
        level=ObservationLevel.MILD,
        score=0.31,
        confidence=0.78,
        method="lab_a_channel_mean",
    )
    assert obs.note is None


def test_visual_observation_accepts_optional_note() -> None:
    obs = VisualObservation(
        feature=ObservationFeature.VISIBLE_TEXTURE,
        level=ObservationLevel.MODERATE,
        score=0.5,
        confidence=0.72,
        method="laplacian_variance",
        note="Estimate only; may be affected by lighting.",
    )
    assert obs.note is not None


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01, 5])
def test_visual_observation_rejects_out_of_range_confidence(bad_confidence: float) -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level=ObservationLevel.MILD,
            score=0.3,
            confidence=bad_confidence,
            method="lab_a_channel_mean",
        )


@pytest.mark.parametrize("bad_score", [-0.01, 1.01, 5])
def test_visual_observation_rejects_out_of_range_score(bad_score: float) -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level=ObservationLevel.MILD,
            score=bad_score,
            confidence=0.5,
            method="lab_a_channel_mean",
        )


def test_visual_observation_requires_method() -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level=ObservationLevel.MILD,
            score=0.3,
            confidence=0.5,
            method="",
        )


def test_visual_observation_rejects_unknown_feature() -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature="acne",
            level=ObservationLevel.MILD,
            score=0.3,
            confidence=0.5,
            method="lab_a_channel_mean",
        )


def test_visual_observation_rejects_unknown_level() -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level="severe_disease",
            score=0.3,
            confidence=0.5,
            method="lab_a_channel_mean",
        )


def test_visual_observation_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        VisualObservation(level=ObservationLevel.MILD, confidence=0.5, score=0.3)


def test_visual_observation_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VisualObservation(
            feature=ObservationFeature.REDNESS,
            level=ObservationLevel.MILD,
            score=0.3,
            confidence=0.5,
            method="lab_a_channel_mean",
            diagnosis="rosacea",
        )


# --- VisualAnalysisResult ---


def _observation(feature: ObservationFeature = ObservationFeature.REDNESS) -> VisualObservation:
    return VisualObservation(
        feature=feature,
        level=ObservationLevel.MILD,
        score=0.3,
        confidence=0.7,
        method="lab_a_channel_mean",
    )


def test_visual_analysis_result_valid() -> None:
    result = VisualAnalysisResult(
        analysis_id=uuid4(),
        image_id=uuid4(),
        observations=[_observation()],
        region_used=RegionSource.DETECTED_FACE,
        limitations=["Lighting can affect this estimate."],
        created_at=datetime.now(timezone.utc),
    )
    assert result.disclaimer.startswith("SkinVision AI provides educational")


def test_visual_analysis_result_defaults_to_no_limitations() -> None:
    result = VisualAnalysisResult(
        analysis_id=uuid4(),
        image_id=uuid4(),
        observations=[],
        region_used=RegionSource.CENTER_CROP_FALLBACK,
        created_at=datetime.now(timezone.utc),
    )
    assert result.limitations == []


def test_visual_analysis_result_rejects_invalid_region_source() -> None:
    with pytest.raises(ValidationError):
        VisualAnalysisResult(
            analysis_id=uuid4(),
            image_id=uuid4(),
            observations=[],
            region_used="face_recognition_match",
            created_at=datetime.now(timezone.utc),
        )


def test_visual_analysis_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        VisualAnalysisResult(
            analysis_id=uuid4(),
            image_id=uuid4(),
            observations=[],
            region_used=RegionSource.DETECTED_FACE,
            created_at=datetime.now(timezone.utc),
            skin_health_score=82,
        )
