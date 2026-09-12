"""Authentication request/response schemas.

``UserRead`` never includes ``hashed_password`` -- there is no field for
it, the same structural guarantee this project already uses elsewhere
(an LLM output schema with no field for a citation it didn't establish;
see docs/agent.md) applied here to credentials instead.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = ["UserCreate", "UserLogin", "UserRead"]


class UserCreate(BaseModel):
    """Payload for ``POST /api/auth/register``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Payload for ``POST /api/auth/login``."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    """A registered user as returned by the API -- never the password
    hash, never a token (the token lives only in the httpOnly cookie).
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str
    session_id: UUID
    created_at: datetime
