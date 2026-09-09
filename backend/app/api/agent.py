"""Agent chat endpoint (Phase 7).

``POST /api/agent/chat`` is the only place a request can trigger the
agent tool-calling loop. Always returns 200 with a structured
``AgentResponse`` -- an LLM failure, a rejected/hallucinating answer, or
a hit tool-call/turn limit is communicated via ``status``/``error``,
never a bare 5xx that would hide the (still-valid) tool trace collected
so far. See docs/agent.md.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.registry import ToolRegistry
from app.agent.schemas import AgentChatRequest, AgentResponse
from app.agent.tools import build_tool_registry
from app.config import Settings, get_settings
from app.core.rate_limit import rate_limit_agent_chat
from app.database import get_db
from app.llm.base import LLMProvider
from app.llm.provider import get_llm_provider
from app.services.agent_service import InvalidChatLinkError, run_agent_chat

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Built once at import time: a ToolRegistry is immutable after
# construction (see app.agent.registry), so there is no benefit to
# rebuilding it per request, and every request sees the exact same set of
# registered tools.
_REGISTRY = build_tool_registry()


def _provider(settings: Settings = Depends(get_settings)) -> LLMProvider:
    return get_llm_provider(settings)


def _registry() -> ToolRegistry:
    return _REGISTRY


@router.post(
    "/chat",
    response_model=AgentResponse,
    status_code=200,
    dependencies=[Depends(rate_limit_agent_chat)],
)
async def agent_chat_endpoint(
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    provider: LLMProvider = Depends(_provider),
    registry: ToolRegistry = Depends(_registry),
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    """Run one agent turn: resolve/persist the chat session and user
    message, run the bounded tool-calling loop, persist the assistant
    message and its tool trace, and return the structured result.

    ``payload.link`` (Phase 8), when given, must name an id the backend
    already computed -- an unknown id is a controlled 400, never a
    silently-ignored or fabricated linkage.
    """
    try:
        return await run_agent_chat(
            db=db, payload=payload, provider=provider, registry=registry, settings=settings
        )
    except InvalidChatLinkError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_chat_link", "message": str(exc)},
        ) from exc
