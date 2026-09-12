"""Authentication endpoints (release-hardening follow-up).

``POST /api/auth/register`` and ``.../login`` set the session as an
httpOnly, ``SameSite=Lax`` cookie -- never a token the response body
hands back for frontend JS to store, which would be readable by any
script on the page (the classic XSS-token-theft class of bug). See
app/services/auth_service.py for the JWT itself and
docs/persistence.md's Security section for the full threat-model
writeup.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.rate_limit import rate_limit_auth
from app.database import get_db
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserRead
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    create_access_token,
    get_current_user,
    register_user,
)
from app.services.session_service import get_or_create_session_for_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_auth_cookie(response: Response, user: User, settings: Settings) -> None:
    token = create_access_token(user.id, settings)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
        max_age=settings.jwt_expiry_days * 24 * 3600,
        path="/",
    )


@router.post("/register", response_model=UserRead, status_code=201, dependencies=[Depends(rate_limit_auth)])
async def register_endpoint(
    payload: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserRead:
    """Create an account and its one session, sign the caller in
    immediately (same as a real login), and return the new user.
    """
    try:
        user = await register_user(db, email=payload.email, password=payload.password)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "email_already_registered", "message": "An account with this email already exists."},
        ) from exc

    session = await get_or_create_session_for_user(db, user, None)
    await db.commit()
    await db.refresh(user)
    await db.refresh(session)

    _set_auth_cookie(response, user, settings)
    return UserRead(id=user.id, email=user.email, session_id=session.id, created_at=user.created_at)


@router.post("/login", response_model=UserRead, status_code=200, dependencies=[Depends(rate_limit_auth)])
async def login_endpoint(
    payload: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserRead:
    try:
        user = await authenticate_user(db, email=payload.email, password=payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Incorrect email or password."},
        ) from exc

    session = await get_or_create_session_for_user(db, user, None)
    await db.commit()

    _set_auth_cookie(response, user, settings)
    return UserRead(id=user.id, email=user.email, session_id=session.id, created_at=user.created_at)


@router.post("/logout", status_code=204, response_model=None)
async def logout_endpoint(response: Response, settings: Settings = Depends(get_settings)) -> None:
    """Clears the auth cookie. Always succeeds, even if the caller wasn't
    signed in -- logout is idempotent, not an authenticated action.
    """
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


@router.get("/me", response_model=UserRead, status_code=200)
async def me_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserRead:
    session = await get_or_create_session_for_user(db, current_user, None)
    await db.commit()
    return UserRead(
        id=current_user.id,
        email=current_user.email,
        session_id=session.id,
        created_at=current_user.created_at,
    )
