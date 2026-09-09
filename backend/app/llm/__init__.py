"""LLM provider abstraction and explanation layer (Phase 6).

base.py defines the ``LLMProvider`` interface every provider implements;
provider.py implements Anthropic, an OpenAI-compatible HTTP client, and a
deterministic offline ``FakeLLMProvider``; schemas.py is the raw
structured-output contract requested from the model; prompts.py is the
system prompt; context.py builds the trusted deterministic payload/ground
truth for one explanation call; validation.py is the anti-hallucination
check run on every response before it is trusted.

The LLM is an explanation/orchestration layer only -- it never determines
ingredient identity, compatibility, severity, or routine ordering. See
docs/llm.md.
"""
