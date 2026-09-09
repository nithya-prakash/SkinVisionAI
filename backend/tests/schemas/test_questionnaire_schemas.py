"""Tests for app.schemas.questionnaire.

Self-reported fields must validate strictly against known enum values --
never silently accept an arbitrary medical-sounding string.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.common import RoutineFrequency, SensitivityPreference, SkinGoal, SkinType
from app.schemas.questionnaire import QuestionnaireResponseCreate


def test_questionnaire_valid_minimal() -> None:
    q = QuestionnaireResponseCreate(analysis_id=uuid4(), skin_goals=[SkinGoal.HYDRATION])
    assert q.skin_type_self_reported == SkinType.UNKNOWN
    assert q.routine_frequency is None
    assert q.current_products == []


def test_questionnaire_valid_full() -> None:
    q = QuestionnaireResponseCreate(
        analysis_id=uuid4(),
        skin_goals=[SkinGoal.HYDRATION, SkinGoal.REDNESS],
        routine_frequency=RoutineFrequency.DAILY,
        current_products=["Gentle Cleanser", "Vitamin C Serum"],
        ingredient_preferences=["niacinamide"],
        ingredient_avoidances=["fragrance"],
        sensitivity_preferences=[SensitivityPreference.FRAGRANCE_FREE],
        skin_type_self_reported=SkinType.COMBINATION,
    )
    assert SkinGoal.REDNESS in q.skin_goals


def test_questionnaire_requires_at_least_one_goal() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireResponseCreate(analysis_id=uuid4(), skin_goals=[])


def test_questionnaire_missing_skin_goals_raises() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireResponseCreate(analysis_id=uuid4())


def test_questionnaire_rejects_unknown_goal() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireResponseCreate(analysis_id=uuid4(), skin_goals=["cure_acne"])


def test_questionnaire_rejects_unknown_skin_type() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireResponseCreate(
            analysis_id=uuid4(),
            skin_goals=[SkinGoal.GENERAL_SKINCARE],
            skin_type_self_reported="rosacea_prone",
        )


def test_questionnaire_rejects_unknown_sensitivity_preference() -> None:
    with pytest.raises(ValidationError):
        QuestionnaireResponseCreate(
            analysis_id=uuid4(),
            skin_goals=[SkinGoal.GENERAL_SKINCARE],
            sensitivity_preferences=["hypoallergenic_certified"],
        )
