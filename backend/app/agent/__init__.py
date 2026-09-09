"""The agentic tool-calling layer (Phase 7).

- ``schemas.py`` -- the public request/response contract
  (``AgentChatRequest``/``AgentResponse``) and the LLM's structured
  final-answer output schema (``AgentFinalAnswerLLMOutput`` -- like Phase
  6's ``ExplanationLLMOutput``, it has no severity/citation fields).
- ``registry.py`` -- ``ToolRegistry``/``ToolDefinition`` and tool
  execution (Pydantic-validated; the only thing ever invoked is a
  pre-registered Python callable looked up by exact name -- no eval/exec/
  dynamic import/arbitrary attribute access anywhere).
- ``tools.py`` -- the concrete tools, each a thin wrapper around an
  existing Phase 4/5 deterministic engine call. No new skincare logic is
  implemented here.
- ``prompts.py`` -- the agent's system prompt and the orchestration rules
  it must follow.
- ``trace.py`` -- ``ToolCallTraceEntry``, the structured record of one
  tool call.
- ``validation.py`` -- reuses/extends Phase 6's anti-hallucination
  machinery (``app.llm.validation``) against the accumulated tool trace
  instead of a single deterministic result.
- ``agent.py`` -- the bounded tool-calling loop itself. Database-free and
  independently testable; ``app.services.agent_service`` wraps it with
  chat-session persistence.

Core principle, unchanged from Phase 6 and enforced the same way
(structurally, not just by prompting): the LLM may decide *which tool to
call* and how to explain the result in plain language. It never decides
*whether an ingredient combination is safe* -- that is exclusively the
deterministic Python tools' output. See docs/agent.md.
"""
