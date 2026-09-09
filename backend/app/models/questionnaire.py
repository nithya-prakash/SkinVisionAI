"""Self-reported questionnaire responses — never treated as medical fact."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class QuestionnaireResponse(UUIDPKMixin, TimestampMixin, Base):
    """A user's self-reported skincare goals, routine, and preferences,
    linked to the analysis they were collected for.
    """

    __tablename__ = "questionnaire_responses"

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skin_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skin_goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    routine_frequency: Mapped[str] = mapped_column(String(32), nullable=True)
    current_products: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ingredient_preferences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ingredient_avoidances: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sensitivity_preferences: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    skin_type_self_reported: Mapped[str] = mapped_column(String(32), nullable=True)
