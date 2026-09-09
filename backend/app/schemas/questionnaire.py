"""Skincare questionnaire schemas.

All fields here are self-reported. They must never be presented downstream
as medically established fact — see ``SkinType`` and ``DISCLAIMER`` in
``app.schemas.common``.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import (
    RoutineFrequency,
    SensitivityPreference,
    SkinGoal,
    SkinType,
)


class QuestionnaireResponseBase(BaseModel):
    """Fields common to questionnaire creation and reads."""

    model_config = ConfigDict(extra="forbid")

    skin_goals: list[SkinGoal] = Field(min_length=1)
    routine_frequency: RoutineFrequency | None = None
    current_products: list[str] = Field(default_factory=list)
    ingredient_preferences: list[str] = Field(default_factory=list)
    ingredient_avoidances: list[str] = Field(default_factory=list)
    sensitivity_preferences: list[SensitivityPreference] = Field(default_factory=list)
    skin_type_self_reported: SkinType = SkinType.UNKNOWN


class QuestionnaireResponseCreate(QuestionnaireResponseBase):
    """Payload accepted when submitting a questionnaire for an analysis."""

    analysis_id: UUID


class QuestionnaireResponseRead(QuestionnaireResponseBase):
    """Questionnaire response as returned by the API."""

    id: UUID
    analysis_id: UUID
    created_at: datetime
