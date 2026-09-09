"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.agent import router as agent_router
from app.api.analysis import router as analysis_router
from app.api.chat import router as chat_router
from app.api.explanations import router as explanations_router
from app.api.health import router as health_router
from app.api.products import router as products_router
from app.api.routine import router as routine_router
from app.api.sessions import router as sessions_router
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Educational skincare insights from computer vision, a deterministic "
        "ingredient/routine engine, and LLM explanation. Not a medical "
        "diagnosis tool."
    ),
    version="0.1.0",
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
app.include_router(analysis_router)
app.include_router(products_router)
app.include_router(routine_router)
app.include_router(explanations_router)
app.include_router(agent_router)
app.include_router(sessions_router)
app.include_router(chat_router)
