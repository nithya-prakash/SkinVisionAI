# Agent Tool-Calling Layer (Phase 7)

**Status: implemented.** This document describes what was actually built,
superseding the earlier Phase 1 design sketch (which planned a vision
tool and a separate deterministic "diagnosis pre-check" layer — neither
exists; see [Deviations from the original sketch](#deviations-from-the-original-sketch)).

## The one rule this document exists to explain

**The LLM may decide *which tool to call*. It never decides *whether an
ingredient combination is safe*.**

```
User
 |
 v
POST /api/agent/chat
 |
 v
Agent loop (app.agent.agent.run_agent)  <---------------------+
 |                                                              |
 v                                                              |
LLMProvider.generate_with_tools(system_prompt, history, tools)  |
 |                                                              |
 +-- tool_call --> ToolRegistry.execute_tool                    |
 |                    |                                         |
 |                    v                                         |
 |               Deterministic engine (Phase 4/5, unchanged)    |
 |                    |                                         |
 |                    v                                         |
 |               ToolCallTraceEntry  --------------------------+
 |                 (tool_result turn appended, loop continues)
 |
 +-- final_answer --> app.agent.validation.validate_agent_answer
                          |
                          v
                     AgentResponse { answer, tool_trace, citations,
                                     limitations, status }
                          |
                          v
                       Frontend (/chat)
```

Same core principle as Phase 6's explanation layer, extended from "explain
one already-computed result" to "choose which deterministic computation(s)
to run, then explain the results" — enforced the same way, structurally
first and heuristically second, not by prompting alone:

- The agent's raw final-answer schema (`AgentFinalAnswerLLMOutput`) has no
  `severity`/`source`/`interactions` field — the same structural
  guarantee Phase 6's `ExplanationLLMOutput` has. Anything a user sees
  with an *exact* value (a severity, a rule_id, a citation) comes from
  `AgentResponse.tool_trace`/`citations`, built by the backend from real
  tool results — never typed by the model.
- The model can only "call a tool" by name-matching into
  `ToolRegistry` — there is no `eval`, `exec`, `importlib`, or
  `getattr`-on-an-arbitrary-name anywhere in the call path (see
  [Security](#security)).
- Every final answer passes `app.agent.validation` (the same heuristic
  checks as Phase 6, reused verbatim) against a ground-truth set built
  from the tool calls that actually ran this turn, before it can reach a
  user.

## Tool registry

`backend/app/agent/registry.py` defines `ToolDefinition` (name,
description, Pydantic input/output model, a pure handler function,
`deterministic=True`) and `ToolRegistry` (register/get/specs). This is
the security-critical boundary: `execute_tool(registry, tool_name,
raw_arguments)` looks `tool_name` up by exact string match in a `dict` —
an unregistered name (`"execute_python"`, `"import"`, anything not
registered) is rejected *before any code runs*, and `raw_arguments` is
always `input_model.model_validate(...)`-checked before the handler is
called. `ToolRegistry.specs()` derives the JSON schema advertised to the
LLM directly from each tool's real `input_model`, so the schema the model
sees and the schema execution validates against can never drift apart.

## The five tools

`backend/app/agent/tools.py` — every handler is a thin wrapper around an
existing Phase 4/5 deterministic engine call; **no new skincare logic was
written for this phase**:

| Tool | Input | Wraps |
|---|---|---|
| `check_ingredient_compatibility` | `{ingredients: [str]}` | `app.ingredients.compatibility.check_ingredient_compatibility` |
| `analyze_product` | name, category?, raw_ingredient_text | the same compatibility engine, over one product's parsed ingredients |
| `compare_products` | `ProductCompareRequest` (reused) | `app.products.comparator.compare_products` |
| `analyze_routine` | `RoutineAnalysisRequest` (reused) | `app.routine.analyzer.analyze_routine` |
| `get_ingredient_information` | `{ingredient: str}` | `app.ingredients.normalizer.normalize_ingredient` |

`check_ingredient_compatibility` and `analyze_product` deliberately return
`CompatibilityResult`, not the full persisted `ProductAnalyzeResponse` —
the same stateless pattern Phase 6's `explanation_service.explain_product`
already established, so the agent can call either tool repeatedly within
one turn without writing a `Product` row per intermediate step. All five
tools are pure, synchronous, side-effect-free: no database access, no
network call, no LLM call inside a tool.

## The bounded agent loop

`backend/app/agent/agent.py::run_agent` is database-free and independently
testable:

```
while turns_used < AGENT_MAX_TURNS:
    response = provider.generate_with_tools(system_prompt, history, tools, FinalAnswerSchema)
    if response is a tool call:
        if tool_calls_used >= AGENT_MAX_TOOL_CALLS: return status=max_tool_calls
        result = execute_tool(registry, name, arguments)   # validated, never raises
        trace.append(result)                                # deduplicated, see below
        history += [tool_call, tool_result]
        continue
    else:
        validate_agent_answer(response.final_answer, trace)  # may reject
        return status=success, answer, trace, citations, limitations
return status=max_tool_calls  # (or tool_error -- see below)
```

Two independent, configurable limits (`Settings.agent_max_tool_calls`
default 5, `Settings.agent_max_turns` default 8 — see `.env.example`):
a "turn" is one round-trip to the LLM (a tool call *or* the final
answer each consume one), while `agent_max_tool_calls` separately bounds
how many tools actually *execute* (a deduplicated repeat doesn't count —
see below). Hitting either limit returns a controlled `AgentResponse`
with whatever trace was collected so far, never a bare error. If the loop
exhausts its turns and *every* attempted tool call failed, the status is
`tool_error` instead of `max_tool_calls` — a meaningfully different
outcome (nothing was ever grounded) that a test can assert on
specifically (`test_all_calls_failing_until_max_turns_reports_tool_error`).

**Deduplication** (`agent.py`'s `cache` dict, keyed by
`f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"`): calling the
same tool with identical arguments twice in one turn reuses the first
call's trace entry instead of re-executing — the model still gets a
`tool_result` turn to keep the conversation coherent, but no duplicate
row is added to the trace and it doesn't count against
`agent_max_tool_calls`.

**Tool result size bound** (`app.agent.trace.bound_tool_result`,
`Settings.agent_max_tool_result_chars` default 20,000): a tool result
whose JSON serialization exceeds the limit is replaced with a small,
always-valid, structured stand-in (`{"truncated": true,
"original_char_count": N, ...}`) rather than truncating mid-string
(which would produce invalid JSON) — before it is ever recorded in the
trace or fed back to the LLM.

## Provider tool-calling contract

Extends the Phase 6 `LLMProvider` interface additively — nothing in
`generate_structured` (still used by the Phase 6 explanation layer)
changed. `backend/app/llm/base.py` adds:

```python
async def generate_with_tools(
    self, system_prompt: str, history: list[ConversationTurn],
    tools: list[ToolSpec], response_model: type[ResponseModel],
) -> AgentLLMResponse[ResponseModel]: ...
```

`ConversationTurn` is a small provider-agnostic shape (`user` /
`assistant_text` / `tool_call` / `tool_result`) the agent loop
accumulates; each concrete provider is stateless per call and converts
the full history to its own wire format every time — there is no
server-side conversation state inside a provider. Every domain tool is
offered via the provider's **native** structured tool/function-calling
mechanism (Anthropic `tools`/`tool_choice`, OpenAI-style
`tools`/`tool_choice`) — never as instructions asking the model to emit
fake JSON in prose. A synthetic `provide_final_answer` tool (shaped by
`response_model`) is always offered alongside the real ones; the model
calling it (instead of a domain tool) is how "I'm done" is signaled, and
is reported back as `AgentLLMResponse.final_answer` rather than
`.tool_call`. Implemented for `AnthropicProvider`, `OpenAICompatibleProvider`,
and `FakeLLMProvider` — see [docs/llm.md](llm.md) for the base provider
abstraction these extend.

## Anti-hallucination validation

`backend/app/agent/validation.py` reuses Phase 6's heuristic textual
checks (`app.llm.validation`'s `OVERCLAIM_PATTERNS`,
`DIAGNOSTIC_CLAIM_PATTERN` (Phase 10), `NUMERIC_CLAIM_PATTERN`,
`URL_PATTERN`, `CITATION_LEAD_IN_PATTERN`, `mentioned_known_ingredients`,
`normalize_for_validation` (Phase 10) — all made public in
`app.llm.validation` specifically so this module could import them
rather than duplicate them) against a ground-truth set built from *every
successful tool call in this turn's trace* (`build_ground_truth`),
instead of Phase 6's single deterministic result:

| Check | Catches |
|---|---|
| Overclaiming phrase ("completely safe", "risk-free", ...) | "No known conflict"/no finding rewritten as "safe" |
| Diagnostic-claim assertion ("you have acne", "this is rosacea", ...) (Phase 10) | The agent crossing the "never diagnose" line — see [docs/safety.md](safety.md#diagnostic-claim-validation) |
| Numeric/percentage claim | An invented score — no tool ever produces one |
| Citation with no known source at all in the trace | A citation with nothing to ground it (e.g. answering without calling a tool) |
| Citation lead-in phrase naming a source not in the trace | A fabricated source (e.g. "AAD 2026") |
| A known ingredient name mentioned that isn't in the trace | An invented ingredient, or a real claim made without the tool call that would ground it |

As in Phase 6, every check above runs on Unicode-normalized text (Phase
10) before matching.

The last two rows are intentionally **stricter** than Phase 6: Phase 6
always has exactly one deterministic result to check against, so "zero
grounding at all" never comes up there. The agent can legitimately answer
with zero tool calls (a greeting, an out-of-scope question), so a
citation phrase or a specific ingredient claim with an *empty* trace is
unambiguously ungrounded and is rejected — this is what makes
"fabricated result without calling the required tool" (the required
adversarial scenario) actually fail. Same bias as Phase 6: deliberately
over-rejects rather than under-rejects. A rejected answer degrades to
`AgentStatus.VALIDATION_ERROR` with the (unaffected, still trustworthy)
tool trace returned — see [Failure behavior](#failure-behavior).

## Trace

`backend/app/agent/trace.py::ToolCallTraceEntry` — `tool_name`,
`arguments`, `result`, `call_index`, `success`, `error`. This is what
makes "how did SkinVision AI reach this answer" reconstructable rather
than re-generated: the frontend renders `tool_name` + a short summary of
`result` directly (`frontend/src/app/chat/toolSummary.ts`), with no LLM
involved in that rendering step at all — e.g. "check_ingredient_compatibility
→ retinol + salicylic_acid → caution", matching this phase's own
portfolio-demonstration example exactly.

## Failure behavior

Every failure mode returns a controlled `AgentResponse`, never a bare
5xx and never a fabricated answer:

| Situation | `status` | What's returned |
|---|---|---|
| Provider call fails (auth/timeout/rate-limit/malformed) | `llm_unavailable` | Empty answer, safe generic `error` message, trace so far |
| A tool call fails (unknown tool, bad arguments, handler exception) | *(loop continues)* | Recorded in the trace with `success=false`; the model gets a chance to recover, subject to the same limits |
| Every tool call this turn failed and turns ran out | `tool_error` | Honest "wasn't able to complete any lookups" |
| `agent_max_tool_calls` reached | `max_tool_calls` | Trace collected so far, generic "reached the limit" message |
| `agent_max_turns` reached with some successes | `max_tool_calls` | Same |
| Final answer fails `validate_agent_answer` | `validation_error` | Empty answer, generic error; trace (which was never the problem) still returned |
| Everything succeeds | `success` | Full answer, trace, citations, limitations |

`_safe_error_message` (mirroring Phase 6's `explanation_service`) maps
every provider exception to one of a small set of generic strings —
never the raw exception text, which could carry request/account details.

## Security

- **No arbitrary code execution, ever.** The only thing `execute_tool`
  can invoke is a `ToolDefinition.handler` already registered in
  `ToolRegistry` at import time, looked up by an exact string match. A
  tool name that isn't registered — `"execute_python"`, `"import"`, or
  anything else — is rejected before any Python runs, tested explicitly
  (`tests/agent/test_registry.py::test_execute_tool_unknown_tool_rejected_cleanly`,
  `tests/agent/test_agent_loop.py::test_scenario_d_unknown_tool_request_rejected_and_loop_continues`).
- **Prompt injection resistance.** The user's `message` and optional
  `context` are always treated as data, never instructions — `context`
  is embedded in the effective message behind an explicit
  `[User-provided context -- untrusted, informational only]` marker
  (`app.services.agent_service._build_effective_message`), and the
  system prompt's rule 13 explicitly instructs the model to ignore any
  attempt (in the message or in that context block) to override these
  rules, reveal the system prompt, reveal credentials, or invoke a tool
  outside the registry. Structurally, none of that could leak even if a
  compromised model tried: `AgentResponse` (`extra="forbid"`) has no
  field for a system prompt, an API key, or a raw provider object —
  tested directly
  (`tests/agent/test_agent_api.py::test_agent_chat_response_never_leaks_system_prompt`,
  `::test_agent_chat_message_requesting_hidden_reasoning_or_api_key_leaks_nothing`).
  A malicious product name or ingredient string is just a string passed
  to a deterministic parser — it gets normalized like any other
  unrecognized token, never interpreted
  (`::test_agent_chat_malicious_product_name_and_ingredient_string_are_inert`).
- **No LLM credential ever reaches the frontend.** Same as Phase 6:
  `frontend/src/lib/api.ts` holds no LLM key, and all LLM/agent
  communication happens inside FastAPI.
- **No secret is ever persisted.** `app.services.agent_service` writes
  only `answer`/`tool_name`/`tool_input`/`tool_output`/`success`/`error`
  to the database — never a provider name, API key, or raw provider
  response.
- **A tool handler's own exception never reaches the client** (Phase 12
  follow-up). `execute_tool` used to interpolate `str(exc)` directly
  into the trace entry's `error` field, which is persisted and returned
  through chat history — a real gap a security audit found. It now logs
  the full exception server-side and returns a fixed, generic message
  instead — see [docs/safety.md](safety.md#tool-call-safety).
- **`POST /api/agent/chat` is rate-limited** (Phase 12 follow-up, 20
  requests/minute per client IP by default) since it carries a real LLM
  token cost in an app with no authentication — see
  [docs/safety.md](safety.md#rate-limiting).

## API

`POST /api/agent/chat` — request: `{message, session_id?, chat_session_id?, context?}`;
response: `AgentResponse` (`answer`, `tool_trace`, `citations`,
`limitations`, `disclaimer`, `status`, `chat_session_id`, `message_id`).
Always `200`; failure is communicated via `status`/an embedded `error`
in the trace/answer, never a bare non-2xx that would hide the (still
valid) trace collected so far. Full shape: [docs/api.md](api.md#agent-chat-phase-7).

## Database

Reuses the Phase 1 `ChatSession`/`ChatMessage`/`AgentTrace` models
(previously defined, never used) rather than creating new tables. One
migration was needed: `agent_traces` gained `success: bool` and
`error_message: str | None` columns (the original Phase 1 schema had no
way to record a failed tool call) — see
`alembic/versions/03336391c4b5_add_agent_traces_success_and_error_.py`.
`alembic check` confirms this is the only schema change this phase
required.

`app.services.agent_service.run_agent_chat` resolves/creates a
`ChatSession` (reusing one by `chat_session_id` alone is sufficient —
this app has no authentication anywhere else either, so requiring the
original anonymous `session_id` to also match would be an inconsistent
extra check with no real security benefit), persists the user message,
runs the (database-free) agent loop, then persists the assistant message
and every `AgentTrace` row.

**Phase 8** adds two things on top, without touching the loop's core
logic: (1) `GET /api/chat/sessions/{id}/messages` reads the same rows
back so a conversation survives a page refresh, and (2) a `ChatSession`
may optionally be linked to one existing analysis/product/routine/
comparison result (`AgentChatRequest.link`, four new nullable
`ChatSession` columns). When linked, `_build_seed_trace` loads that
row's result and hands it to `run_agent`'s `seed_trace` parameter, which
treats it exactly like a real executed tool call — included in the trace
and in `app.agent.validation`'s ground truth from the very first turn,
not a special-cased trusted input. See
[docs/persistence.md](persistence.md#chat-lifecycle) for the full
request/response shapes and the database relationships.

### Conversational memory: deliberately request-scoped, not long-term

Per this phase's explicit scope: **no embeddings, no vector database, no
semantic memory, no user profiling.** When a request includes
`chat_session_id`, `agent_service._load_prior_turns` replays up to the
last 10 persisted messages (plain user/assistant *text* only) as
context for this turn's `generate_with_tools` calls. What is **not**
replayed: any prior turn's tool-call/tool-result exchange — those exist
only within the single request that produced them and are never written
back into a later turn's history. This keeps memory small, bounded, and
free of stale tool state, at the cost of the model not being able to
literally recall an earlier turn's raw tool output (it can, and typically
should, just call the tool again — deduplication only applies within one
turn).

## Frontend

`frontend/src/app/chat/page.tsx` replaces the Phase 1 placeholder with a
real chat UI: message bubbles, a status badge for any non-`success`
response, and a `<details>` "How SkinVision AI reached this answer"
section per assistant message rendering the tool trace
(`toolSummary.ts` — a purely presentational formatter, no
skincare-domain judgment) and citations. The frontend makes zero LLM
calls, computes zero skincare logic, and never decides a severity or a
routine order — it only renders what `AgentResponse` already contains,
consistent with every other page in this project.

## Testing without a live LLM

`tests/agent/test_registry.py`, `test_tools.py`, `test_agent_loop.py`,
`test_trace.py`, and `test_validation.py` are entirely offline — no
database, no network, no API key — verified with `docker run --network
none`. `test_agent_loop.py` drives `FakeLLMProvider` via a pre-programmed
`agent_script` (a list of `AgentLLMResponse` steps): exact, deterministic
control over what the model "does" on each turn, with zero text-guessing,
covering all 5 required scenarios (single tool call, `compare_products`,
`analyze_routine`, an unknown-tool request, and a fabricated answer with
no tool call), multi-tool reasoning, both limits, tool failure, LLM
failure (including mid-loop after a partial success), deduplication, and
determinism. `tests/agent/test_agent_api.py` additionally exercises the
real ASGI app + real PostgreSQL (chat persistence is genuinely
database-backed, unlike Phase 6's stateless explanation endpoints, so
this one file needs a reachable database — see the completion report for
the exact offline-verification split).

For local development or Docker verification without a real provider
key, `LLM_PROVIDER=fake` also works for the agent: `FakeLLMProvider`'s
default (unscripted) behavior scans the user's own message for known
ingredient names (reusing the same `mentioned_known_ingredients` helper
the validator uses) and calls `check_ingredient_compatibility` or
`get_ingredient_information` accordingly — it can only ever call a tool
with an ingredient the user actually typed, never a guessed one — then
summarizes whatever the tool(s) returned. It does not attempt
routine/comparison intent detection from free text (that would require
real language understanding); those flows are demonstrated live via
`agent_script`-driven tests instead.

## Deviations from the original sketch

The Phase 1 placeholder this document replaces sketched a larger design
than this phase actually needed:

- **No `analyze_skin_image` tool.** This phase's tool list (5 tools) was
  specified explicitly and does not include vision; Phase 3's visual
  observations remain reachable only through their own existing
  endpoint, not through the agent, in this phase.
- **No separate deterministic "diagnosis pre-check" layer.** The
  original sketch planned intercepting diagnosis-seeking messages before
  generation with a fixed keyword check. This phase instead relies on
  the system prompt's explicit rules (never diagnose, never prescribe,
  never claim medical certainty, treat a visual-analysis finding like
  "pronounced redness" as an observation and never as a diagnosis) plus
  the same post-hoc validation as every other claim. A dedicated
  pre-check may be worth adding later if a real model's refusal
  behavior proves unreliable in practice; nothing observed while
  building this phase (deterministic `FakeLLMProvider`-driven tests
  only) demonstrates that need yet.
- **No `generate_skincare_insights` "assembly" tool.** The final answer
  is produced by the same `provide_final_answer` structured-output step
  every provider already exposes (see [Provider tool-calling
  contract](#provider-tool-calling-contract)) — a separate assembly tool
  would have been redundant.

## Limitations

- The anti-hallucination validator is the same heuristic
  regex/set-membership approach as Phase 6, with the same known
  weaknesses (can be fooled by indirect phrasing; can over-reject
  legitimate phrasing) — see [docs/llm.md](llm.md#known-limitations).
- `FakeLLMProvider`'s unscripted default only recognizes ingredient
  names already in this system's small, curated rule set, and only
  attempts single-ingredient/pairwise-compatibility tool selection — it
  is a demo convenience, not a substitute for a real model's reasoning.
- Conversational memory is request-scoped plain text only (see
  [above](#conversational-memory-deliberately-request-scoped-not-long-term)) —
  by design, not an oversight.
- No multi-agent orchestration, no autonomous planning beyond one
  bounded tool-calling loop per user turn, no heavy agent framework —
  per this phase's explicit "do not overengineer" instruction.
