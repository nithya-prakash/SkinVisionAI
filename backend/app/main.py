"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.agent import router as agent_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.explanations import router as explanations_router
from app.api.health import router as health_router
from app.api.products import router as products_router
from app.api.routine import router as routine_router
from app.api.sessions import router as sessions_router
from app.config import get_settings
from app.core.image_cleanup import cleanup_expired_images
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

settings = get_settings()


async def _image_cleanup_loop(interval_hours: float) -> None:
    """Runs ``cleanup_expired_images`` on a fixed interval for the life of
    the process. A single sweep's failure is logged and the loop keeps
    going -- one bad sweep must never take the whole app down.
    """
    interval_seconds = max(interval_hours, 0.01) * 3600
    while True:
        try:
            async with AsyncSessionLocal() as db:
                cleaned = await cleanup_expired_images(db, settings)
            if cleaned:
                logger.info("image_cleanup_loop_swept count=%d", cleaned)
        except Exception:
            logger.exception("image_cleanup_loop_sweep_failed")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_image_cleanup_loop(settings.image_cleanup_interval_hours))
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Educational skincare insights from computer vision, a deterministic "
        "ingredient/routine engine, and LLM explanation. Not a medical "
        "diagnosis tool."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for an exception no router/service already turned into a
    controlled ``HTTPException`` (Phase 10). FastAPI dispatches
    ``HTTPException`` to its own, more specific built-in handler first --
    registering this for the bare ``Exception`` type never intercepts an
    intentional 4xx, only a genuinely unexpected failure (a DB error, an
    exhausted resource, a future bug). Logs the full exception
    server-side only, and returns the same ``{code, message}`` JSON
    shape every other error response in this app already uses, instead
    of Starlette's default plain-text 500 -- never a stack trace, a
    filesystem path, or any other internal detail in the response body.
    """
    logger.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(analysis_router)
app.include_router(products_router)
app.include_router(routine_router)
app.include_router(explanations_router)
app.include_router(agent_router)
app.include_router(sessions_router)
app.include_router(chat_router)
