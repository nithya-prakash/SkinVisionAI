"""Health check endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.config import get_settings

    settings = get_settings()
    return HealthResponse(
        status="ok", app_name=settings.app_name, environment=settings.environment
    )
