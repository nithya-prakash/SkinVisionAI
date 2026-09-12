"""Registered user identity — see app.services.auth_service for password
hashing and JWT issuance. A user owns exactly one UserSession (created at
registration); nothing about auth or a session's ownership lives outside
these two closely-related tables.
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    """A registered account. ``hashed_password`` is a bcrypt hash --
    never a plaintext password, and never returned by any API schema
    (see app.schemas.auth.UserRead).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(60), nullable=False)
