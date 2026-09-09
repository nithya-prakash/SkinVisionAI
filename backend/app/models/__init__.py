"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``Base.metadata.create_all`` (tests) see the full schema.
"""
from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.session import UserSession
from app.models.image import ImageMetadata
from app.models.analysis import SkinAnalysis
from app.models.questionnaire import QuestionnaireResponse
from app.models.product import Ingredient, Product
from app.models.routine import Routine, RoutineItem
from app.models.routine_analysis import RoutineAnalysisRecord
from app.models.comparison import ComparisonRecord
from app.models.chat import AgentTrace, ChatMessage, ChatSession

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPKMixin",
    "UserSession",
    "ImageMetadata",
    "SkinAnalysis",
    "QuestionnaireResponse",
    "Ingredient",
    "Product",
    "Routine",
    "RoutineItem",
    "RoutineAnalysisRecord",
    "ComparisonRecord",
    "ChatSession",
    "ChatMessage",
    "AgentTrace",
]
