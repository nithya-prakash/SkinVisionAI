"""Async SQLAlchemy engine/session setup.

Phase 1 only establishes the plumbing (engine, session factory, declarative
base, FastAPI dependency). Table definitions live in ``app.models`` and are
wired to Alembic for migrations starting Phase 1's initial revision.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# NullPool: this app's traffic never justifies connection pooling, and
# pooling actively breaks async test suites -- a pooled asyncpg connection
# is bound to the event loop that created it, so reusing one across
# pytest-asyncio's per-test event loops raises "another operation is in
# progress". NullPool opens a fresh connection per checkout instead.
engine = create_async_engine(
    settings.database_url, echo=settings.debug, future=True, poolclass=NullPool
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
