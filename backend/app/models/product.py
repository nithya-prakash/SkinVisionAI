"""Product and canonical Ingredient reference tables."""
from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Ingredient(UUIDPKMixin, TimestampMixin, Base):
    """A canonical ingredient entry, seeded from ``rules/ingredients/aliases.json``
    (Phase 4). Not a general-purpose cosmetic-chemistry database.
    """

    __tablename__ = "ingredients"

    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(64), nullable=True)


class Product(UUIDPKMixin, TimestampMixin, Base):
    """A user-entered product: a name plus a raw and normalized ingredient
    list, and the deterministic compatibility-engine result for it
    (Phase 4). ``analysis_result`` holds the full serialized
    ``CompatibilityResult`` (interactions, unknown ingredients,
    limitations) so it need not be recomputed on every read.
    """

    __tablename__ = "products"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=True)
    raw_ingredient_text: Mapped[str] = mapped_column(String, nullable=True)
    normalized_ingredients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    analysis_result: Mapped[dict] = mapped_column(JSON, nullable=True)
