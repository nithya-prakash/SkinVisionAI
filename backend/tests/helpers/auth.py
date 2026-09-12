"""Test helper for creating a throwaway User + their UserSession directly
against the database (no HTTP round-trip) -- for service-layer tests that
need a real, owned session to satisfy UserSession.user_id's NOT NULL
constraint but aren't testing the API/auth layer itself. API-level tests
should use the ``authenticated_client`` fixture (conftest.py) instead.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import UserSession
from app.models.user import User
from app.services.auth_service import hash_password


async def make_user_and_session(db: AsyncSession) -> tuple[User, UserSession]:
    user = User(
        email=f"test-{uuid.uuid4().hex}@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    db.add(user)
    await db.flush()

    session = UserSession(user_id=user.id)
    db.add(session)
    await db.flush()

    return user, session
