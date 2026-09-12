"""Registration, login, and the ``get_current_user`` dependency every
protected route uses.

Password hashing is bcrypt directly (``bcrypt.hashpw``/``checkpw``), no
passlib abstraction layer -- this project prefers small, auditable, hand-
rolled code over an extra dependency for something this contained (same
reasoning as the hand-rolled rate limiter in app/core/rate_limit.py).
Sessions are a JWT in an httpOnly cookie (never a bearer token a frontend
script could read) -- see app/api/auth.py for where the cookie is set.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models.session import UserSession
from app.models.user import User
from app.services.session_service import get_or_create_session_for_user

__all__ = [
    "InvalidCredentialsError",
    "EmailAlreadyRegisteredError",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "register_user",
    "authenticate_user",
    "get_current_user",
]


class InvalidCredentialsError(Exception):
    """Wrong email or wrong password. Deliberately not distinguished in
    the message returned to the client (``app/api/auth.py``) -- telling
    an attacker "that email doesn't exist" vs. "wrong password" would
    leak which emails are registered.
    """


class EmailAlreadyRegisteredError(Exception):
    """Raised by ``register_user`` for a duplicate email."""


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: UUID, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> UUID | None:
    """Returns the user id the token was issued for, or ``None`` for any
    invalid/expired/malformed token -- never raises, so callers (``get_
    current_user``) have one place that turns "no valid token" into 401.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


async def register_user(db: AsyncSession, *, email: str, password: str) -> User:
    """Create a new account and its one-and-only session in the same
    transaction. Raises ``EmailAlreadyRegisteredError`` for a duplicate
    email -- checked explicitly rather than relying on the database's
    unique-constraint error, so the API layer gets a clean, expected
    exception type instead of parsing an IntegrityError.
    """
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyRegisteredError(email)

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.flush()

    db.add(UserSession(user_id=user.id))
    await db.flush()

    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User:
    """Raises ``InvalidCredentialsError`` for either an unknown email or
    a wrong password -- see that exception's docstring for why the two
    aren't distinguished.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency: ``Depends(get_current_user)`` on every
    protected route. Reads the JWT from the httpOnly cookie (never a
    header a frontend script would have to manage), and raises a clean
    401 for anything short of a fully valid token naming a real user --
    missing cookie, expired token, tampered signature, or a user that
    was somehow deleted after the token was issued all collapse to the
    same generic 401, never a distinguishing error that would help an
    attacker narrow down which case they hit.
    """
    token = request.cookies.get(settings.auth_cookie_name)
    user_id = decode_access_token(token, settings) if token else None
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "not_authenticated", "message": "Sign in to continue."},
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "not_authenticated", "message": "Sign in to continue."},
        )
    return user


async def get_current_user_session(
    db: AsyncSession, user: User, session_id: str | None = None
) -> UserSession:
    """Convenience wrapper most routes actually want: the authenticated
    user's own (ownership-checked) session. Thin pass-through to
    ``session_service.get_or_create_session_for_user`` -- kept here too
    so route modules only need one import for "who is this and what's
    their session."
    """
    return await get_or_create_session_for_user(db, user, session_id)
