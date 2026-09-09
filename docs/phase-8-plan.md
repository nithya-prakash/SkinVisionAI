# Phase 8 Plan: Application Integration & Persistence

**Status: plan only — nothing in this document has been implemented.**
Per the Phase 8 prompt: write this plan, then STOP. Do not implement
anything below until it is explicitly approved.

This plan is grounded in an actual inspection of the Phase 1–7 codebase
(file/class/endpoint names below are real, not illustrative) done
immediately before writing it, plus a confirmed fresh test run: **550
tests passing** (`docker run ... python -m pytest -q`) against the
current `skinvision-ai-api:latest` image and a running Postgres.

---

## 1. Current architecture discovered from the repository

- **Backend**: FastAPI (`backend/app/main.py`) with 6 routers already
  mounted — `health`, `analysis`, `products`, `routine`, `explanations`
  (Ph. 6), `agent` (Ph. 7). Layering is consistent throughout: thin API
  routers → a `services/*_service.py` module doing orchestration + DB
  work → a domain package (`ingredients/`, `routine/`, `products/`,
  `vision/`, `llm/`, `agent/`) doing the actual deterministic/LLM work.
  Async SQLAlchemy (`NullPool`, per-request session via `get_db`),
  Alembic migrations, Pydantic v2 schemas everywhere (`extra="forbid"`
  throughout — no endpoint accepts or returns an unvalidated shape).
- **Frontend**: Next.js App Router, 6 routes — `/`, `/analyze`,
  `/results/[id]`, `/routine`, `/compare`, `/chat`. All client components
  calling a single typed API client (`frontend/src/lib/api.ts`) that
  contains zero skincare logic — confirmed still true, nothing to
  change about that invariant.
- **Sessions today**: `UserSession` (Ph. 1) is the only identity concept,
  anonymous, no auth. It is created ad hoc by
  `app.services.session_service.get_or_create_session` whenever a
  request supplies no known `session_id` — which is **every** current
  frontend request except Ph. 7 chat's `chat_session_id` continuation.
  Concretely: `/analyze`, `/compare`, `/routine` never send a
  `session_id` today, so every visit mints a brand-new, immediately
  orphaned `UserSession` row. There is no client-side session
  persistence (no `localStorage`, no cookie) anywhere in the frontend.
- **The chat/agent stack (Ph. 7) already does real persistence**:
  `ChatSession` → `ChatMessage` → `AgentTrace`, via
  `app.services.agent_service.run_agent_chat`, is the one part of the
  app that already behaves like Phase 8 wants the rest to behave —
  continuable via `chat_session_id`, with a bounded (last 10 messages)
  plain-text history replay. This is the template Phase 8's analysis
  retrieval work should follow, not a new pattern to invent.

## 2. Existing models and what they currently store

All in `backend/app/models/`, registered on `Base.metadata` via
`app/models/__init__.py` (7 files, 11 model classes):

| Model | Status | What it stores |
|---|---|---|
| `UserSession` | used | Anonymous identity only (`id`, timestamps) |
| `ImageMetadata` | used | Upload metadata + `quality_result` (JSON `ImageQualityResult`); `storage_path` nullable when retention is disabled |
| `SkinAnalysis` | **used, but never read back** | `session_id`, `image_id`, `status` (`AnalysisStatus` — `pending/image_uploaded/analyzing/completed/failed`), `visual_observations` (JSON list), `structured_response` (JSON `VisualAnalysisResult`) — **fully populated by `vision_service.analyze_visual_features`, but no endpoint ever reads a row back; `/results/[id]` re-runs the POST every time instead of fetching.** `status` never actually reaches `analyzing` or `failed` in code today — only `image_uploaded` and `completed` are ever set. |
| `QuestionnaireResponse` | **defined, unused since Ph. 1** | Self-reported goals/routine/sensitivities — no endpoint reads or writes it anywhere in Ph. 1–7 |
| `Ingredient` | **defined, unused since Ph. 1** | The ingredient engine's source of truth is the versioned JSON rule files (`app/ingredients/rules.py`), not this table — documented as intentional in `docs/ingredients.md` |
| `Product` | used | `session_id`, `name`, `category`, `raw_ingredient_text`, `normalized_ingredients`, **`analysis_result` (JSON `CompatibilityResult`)** — the existing precedent for "persist a JSON domain result next to its request fields" |
| `Routine` / `RoutineItem` | **defined, unused since Ph. 1** | Models a *user-curated, persisted* AM/PM sequence of existing `Product` rows (`product_id` + `time_of_day` + `step_order`) — **a different concept from the Ph. 5 `RoutineAnalysisRequest`/`Result` shape**, which takes ad-hoc raw ingredient text per product and is not tied to persisted `Product` rows at all. There is no CRUD endpoint for these tables yet. |
| `ChatSession` | used (Ph. 7) | `session_id` only — no reference to an analysis/product/routine/comparison yet |
| `ChatMessage` | used (Ph. 7) | `chat_session_id`, `role`, `content`, `structured_response` (JSON) |
| `AgentTrace` | used (Ph. 7) | `chat_message_id`, `tool_name`, `tool_input`, `tool_output`, `step_order`, `success`, `error_message` (the last two added in Ph. 7's migration) |

**No table exists today for a persisted routine-*analysis* result or a
persisted product-*comparison* result** — `POST /api/routine/analyze` and
`POST /api/products/compare` (Ph. 5) are deliberately, explicitly
stateless; `docs/routine.md` has a dedicated section justifying this
("Both new endpoints are deliberately stateless... `alembic check`
reports no new migration was needed"). Phase 6's three
`/api/explanations/*` endpoints are equally stateless by the same
rationale (re-run the deterministic engine fresh every call so a client
can never submit forged "already computed" facts).

## 3. Existing API endpoints

| Method + path | Router | Persists? | Notes |
|---|---|---|---|
| `GET /health` | health | no | |
| `POST /api/analysis/upload` | analysis | **yes** | Creates `UserSession` (if needed) + `ImageMetadata` + `SkinAnalysis` (status `image_uploaded`) |
| `POST /api/analysis/{id}/visual-analysis` | analysis | **yes** (updates the same row) | No GET counterpart exists |
| `POST /api/products/analyze` | products | **yes** | Creates `Product` with `analysis_result` |
| `POST /api/products/compare` | products | no | Stateless by design (Ph. 5) |
| `POST /api/routine/analyze` | routine | no | Stateless by design (Ph. 5) |
| `POST /api/explanations/product` \| `/compare` \| `/routine` | explanations | no | Stateless by design (Ph. 6) — re-runs the Ph. 4/5 engine itself |
| `POST /api/agent/chat` | agent | **yes** | The only endpoint with a continuation mechanism (`chat_session_id`) |

**Confirmed gap** (the analysis router's own docstring says so):
`GET /api/analysis/{id}` does not exist. No session-level endpoints
(`GET /api/sessions/*`) exist. No chat-history retrieval endpoints
(`GET /api/chat/sessions/*`) exist.

## 4. Existing frontend routes

| Route | Behavior today | Session-aware? |
|---|---|---|
| `/` | Static landing/nav | — |
| `/analyze` | Upload → shows quality result inline → link to `/results/{analysis_id}` | Never sends `session_id` |
| `/results/[id]` | On mount, **always POSTs** `/visual-analysis` for `analysisId` from the URL (re-running the CV pipeline every visit/refresh, not fetching a persisted result) | No session concept at all |
| `/routine` | Client-side form → `POST /api/explanations/routine` (Ph. 6 wired this in) → renders analysis + AI explanation | Never sends `session_id` |
| `/compare` | Same pattern for single-product analyze and two-product compare, via the Ph. 6 explanation endpoints | Never sends `session_id` |
| `/chat` | Full agent chat UI (Ph. 7): tracks `chatSessionId` in React state only (lost on refresh) | `chatSessionId` only, in memory, not persisted client-side |

**Confirmed gap**: nothing persists an application session id client-side
(no `localStorage`/cookie anywhere in `frontend/src/`), so a page refresh
anywhere loses all session continuity, and `/chat`'s conversation is lost
on refresh even though the backend already retains it.

## 5. Persistence gaps (synthesis of §2–4)

1. `SkinAnalysis` rows are fully populated but **unreadable** — no `GET`.
2. `/results/[id]` **recomputes instead of retrieving**, and does not
   represent "quality rejected" / "not yet visually analyzed" as
   distinct, explicit states — it just always tries to POST.
3. `SkinAnalysis.status` never reaches `analyzing` (no page needs a
   polling/in-progress state today since Ph. 3 is synchronous, so this is
   low priority) or `failed` (an unhandled exception in
   `analyze_visual_features` today leaves the row silently stuck at
   `image_uploaded` forever — worth fixing regardless of the rest of
   Phase 8).
4. No persisted record of a routine analysis or a product comparison —
   by *deliberate, documented* Phase 5 design, not an oversight. Whether
   Phase 8 should change that is a real design decision, not a gap to
   silently fill (see §6's open question).
5. No session-level retrieval (`GET /api/sessions/{id}`, `.../analyses`,
   `.../chats`) — none of these endpoints exist.
6. No chat-history retrieval endpoint — a client can only see chat
   messages it already holds in memory from prior responses; there is no
   way to reload a conversation after a refresh even though it is fully
   persisted server-side already.
7. `ChatSession` cannot reference an existing analysis/product/routine/
   comparison — the agent has no way to be handed "the user's last
   uploaded photo" or "the routine they just analyzed" as trusted
   context; every chat turn today starts from zero deterministic context
   except what the user's own message text causes a tool call to
   establish.
8. No client-side session persistence at all (§4) — every page load is
   functionally a new anonymous visitor server-side.

## 6. Proposed database changes

All additive (`ADD COLUMN` / `CREATE TABLE`), nothing destructive, no
existing column altered or dropped. Every new table follows the existing
`UUIDPKMixin, TimestampMixin, Base` pattern.

### 6a. `AgentTrace`-style tables for routine analysis and comparison

**Open question — needs your decision, not mine to make silently**,
because Phase 5 documented statelessness as a deliberate architectural
choice (`docs/routine.md`) and Phase 8's own rules say "do not create
redundant tables for the sake of it" while also saying "persist results
users reasonably expect to retrieve later." Three options:

- **(a) Leave `/api/routine/analyze` and `/api/products/compare` fully
  stateless, exactly as today.** Add new, separate endpoints
  (`POST /api/routine/analyses`, `POST /api/comparisons`) that *do*
  persist, for callers that want a retrievable id. Zero risk to existing
  behavior or existing docs; most conservative.
- **(b) Make the existing endpoints always persist**, mirroring how
  `Product.analysis_result` already works for single-product analysis.
  Simplest for the frontend (no new endpoints to learn), but reverses
  Phase 5's documented "deliberately stateless" rationale and requires
  rewriting that section of `docs/routine.md`.
- **(c) Opt-in persistence on the existing endpoints** via an optional
  request field (default `false`); when set, the response gains an
  optional `id` (backward compatible — existing callers who never set
  the flag see byte-identical responses to today).

**My recommendation is (c)** — it satisfies "persist what's reasonably
expected to be retrieved" without silently reversing a documented design
decision or duplicating endpoints. New table (name to be finalized, e.g.
`RoutineAnalysisRecord` / `ComparisonRecord` — avoiding `Routine`, which
already means something different): `id`, `session_id` (FK), `request`
(JSON), `result` (JSON), timestamps. This mirrors `Product`'s
request-plus-`analysis_result` shape exactly.

### 6b. `ChatSession` gains optional linkage columns

```python
skin_analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skin_analyses.id", ondelete="SET NULL"), nullable=True)
product_id:       Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
routine_analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("<new table>.id", ondelete="SET NULL"), nullable=True)
comparison_id:    Mapped[uuid.UUID | None] = mapped_column(ForeignKey("<new table>.id", ondelete="SET NULL"), nullable=True)
```

All nullable, `ondelete="SET NULL"` (deleting a referenced analysis must
never cascade-delete a conversation). Populated only when a chat is
explicitly started "about" an existing result (see §11); an ordinary
`/chat` visit leaves all four `NULL`, unchanged from today's behavior.

### 6c. `agent_service`/`agent.py` context-loading extension

Not a schema change, but depends on 6b: when a `ChatSession` has a
linkage set, `run_agent_chat` loads that row's already-computed
JSON result and injects it into the agent loop's history as a
`ConversationTurn(kind="tool_result", ...)` **as if a tool had already
run** — never as raw untrusted text, and never bypassing
`app.agent.validation`, which still checks the final answer against
whatever is actually in the trace. This is the mechanism behind "What
about this product with the routine I analyzed earlier?" in §11.

### 6d. `SkinAnalysis.status` behavior fix (no schema change)

Wrap `analyze_visual_features`'s pipeline call so an unexpected exception
sets `status = AnalysisStatus.FAILED` and commits before re-raising,
instead of leaving the row silently stuck at `image_uploaded`. Small,
independent, low-risk fix — flagging here so it isn't missed, not because
it needs a migration.

### What is explicitly NOT proposed

- No changes to `Ingredient`, `Routine`/`RoutineItem`, or
  `QuestionnaireResponse` — still out of scope; nothing in Phase 8's
  brief needs persisted-CRUD routines or the questionnaire.
  `Routine`/`RoutineItem` remain reserved for a possible future
  "save this AM/PM sequence" feature, distinct from routine *analysis*.
- No new "generic session activity feed" table — `GET .../analyses` and
  `.../chats` (§9) are simple filtered queries against existing tables,
  not a new denormalized table.

## 7. Proposed API changes

New routers: `backend/app/api/sessions.py`, `backend/app/api/chat.py`
(history retrieval — distinct from `backend/app/api/agent.py`, which
keeps owning `POST /api/agent/chat` itself). Extend
`backend/app/api/analysis.py` in place (it already owns the analysis
lifecycle).

| Method + path | New/existing | Purpose |
|---|---|---|
| `POST /api/sessions` | new | Create a session explicitly (`SessionRead`) |
| `GET /api/sessions/{id}` | new | Session metadata; 404 if unknown |
| `GET /api/sessions/{id}/analyses` | new | This session's `SkinAnalysis` rows (summary shape, not full observations) |
| `GET /api/sessions/{id}/chats` | new | This session's `ChatSession` rows (summary shape) |
| `GET /api/analysis/{id}` | new | Full `SkinAnalysisRead`-shaped response (see §10) |
| `GET /api/chat/sessions/{id}` | new | One chat session's metadata + linkage (§6b) |
| `GET /api/chat/sessions/{id}/messages` | new | That session's `ChatMessage` rows + each assistant message's `AgentTrace` rows, safely shaped (no hidden reasoning — same fields already exposed by `POST /api/agent/chat`'s `tool_trace`) |
| `POST /api/routine/analyze`, `POST /api/products/compare` | existing, extended | Optional `persist: bool = false` field (§6a option c); response gains optional `id` |
| `POST /api/agent/chat` | existing, extended | Optional `link` field (e.g. `{"skin_analysis_id": ...}` — exactly one of the four kinds) to set §6b's linkage when starting a chat about a specific result |

Every new/changed response uses a dedicated Pydantic model
(`app.schemas.session`, extending `app.schemas.analysis`/`app.schemas.chat`
as needed) — never a raw SQLAlchemy model, matching the existing
convention exactly. Unknown ids return `404` with the same
`{"code": ..., "message": ...}` shape `UploadValidationError`/
`VisualAnalysisError` already use.

## 8. Proposed frontend changes

- **New**: `frontend/src/lib/session.ts` — reads/creates an application
  `session_id` in `localStorage` (key TBD, e.g. `skinvision_session_id`),
  a plain opaque UUID string, never a secret. Every API client function
  that currently omits `session_id` (`analyzeProduct`-family,
  `analyzeRoutine`, `compareProducts`, `sendAgentChatMessage`, the upload
  call) starts passing it. `lib/api.ts` gains `getSession`,
  `listSessionAnalyses`, `listSessionChats`, `getAnalysis`,
  `getChatSession`, `getChatMessages`.
- **`/results/[id]`**: on mount, call the new `GET /api/analysis/{id}`
  first. Render its state explicitly (`quality_pending` /
  `quality_rejected` / `ready_for_visual_analysis` /
  `visual_analysis_complete` / `failed`) instead of unconditionally
  POSTing. Keep a "Re-run analysis" action that still POSTs
  `/visual-analysis` explicitly (deterministic + idempotent already, so
  this stays safe) rather than doing so implicitly on every mount.
- **`/chat`**: persist `chatSessionId` to `localStorage` alongside the
  app session id; on mount, if one exists, call
  `GET /api/chat/sessions/{id}/messages` and hydrate the message list
  (including re-rendering each assistant message's trace) instead of
  starting empty.
- **`/analyze`, `/routine`, `/compare`**: no visible UX change required
  by Phase 8's brief beyond sending `session_id` on every call; if §6a
  option (c) is approved, add a lightweight, non-blocking "Save this
  result" affordance that sets `persist: true` and shows the returned id
  — kept minimal, not a redesign.
- Frontend still computes **zero** skincare logic — every new file above
  only fetches/stores/renders already-computed backend state, consistent
  with the existing, tested invariant in `lib/api.ts`'s own module
  docstring.

## 9. Session lifecycle

```
No session_id in localStorage
        |
        v
POST /api/sessions  ->  UserSession row created  ->  id stored in localStorage
        |
        v
Every subsequent request (upload, analyze, compare, routine, chat)
sends that session_id
        |
        v
get_or_create_session(db, session_id) reuses the existing row
(already-existing Ph. 1 helper -- unchanged)
        |
        v
GET /api/sessions/{id}/analyses | /chats  ->  lets a client reconstruct
"what has this session done" after a refresh or on a "history" view
```

Unknown/garbage `session_id` sent by a client: `get_or_create_session`
already handles this today (falls back to creating a new one on an
invalid/unknown id) for write paths; the new **read** endpoints
(`GET /api/sessions/{id}`) must instead 404 on an unknown id rather than
silently fabricating a session — per the prompt's explicit "do not
silently create unrelated sessions for endpoints that reference an
existing ID."

## 10. Analysis lifecycle

Using the existing `AnalysisStatus` enum (`app.schemas.analysis`) as-is
— no new states invented, just actually wiring the two that already
exist but are never set:

```
image_uploaded  (POST /api/analysis/upload; quality result attached)
      |
      +-- quality.is_acceptable == False --> stays image_uploaded,
      |     represented to the client as "quality_rejected" (derived,
      |     not a stored state -- see below)
      |
      v (quality accepted, client explicitly triggers analysis)
  analyzing  (set at the start of analyze_visual_features -- new)
      |
      +-- exception --> failed  (new -- §6d)
      |
      v success
  completed  (unchanged -- already set today)
```

`GET /api/analysis/{id}` response derives a client-facing status from
`(SkinAnalysis.status, ImageMetadata.quality_result.is_acceptable)`
rather than storing a redundant fifth stored value — e.g. an
`image_uploaded` row with an unacceptable quality result is reported as
`"quality_rejected"` to the client, one with an acceptable result as
`"ready_for_visual_analysis"`. This keeps the stored enum small
(matching the existing schema) while still giving the frontend an
explicit, non-fabricated state to render. `analyzing` is set even though
Phase 3's pipeline is synchronous today — cheap to add now, and correct
if the pipeline ever becomes async later, without another migration.

Repeated `POST /visual-analysis` calls remain exactly as idempotent as
today (same deterministic pipeline, same overwrite-in-place behavior) —
Phase 8 does not change that endpoint's semantics, only adds a way to
retrieve its result without re-running it.

## 11. Chat lifecycle

```
Frontend has (or creates) an app session_id and, optionally, a chat_session_id
        |
        v
POST /api/agent/chat {message, session_id, chat_session_id?, link?}
        |
        v
agent_service.run_agent_chat:
  1. resolve/create ChatSession (reusing by chat_session_id alone is
     sufficient -- unchanged Ph. 7 behavior)
  2. if `link` given (new, §7) and chat_session_id is newly created,
     set the corresponding §6b column
  3. load bounded prior text turns (unchanged Ph. 7 behavior, last 10)
  4. if this ChatSession has a §6b linkage, load that row's persisted
     JSON result and inject it as an already-satisfied tool_result turn
     (§6c) -- the agent can reference it without re-calling a tool, but
     app.agent.validation still checks the final answer against
     whatever ends up in the trace, linked-context included
  5. run_agent (unchanged, DB-free, Ph. 7)
  6. persist assistant ChatMessage + AgentTrace rows (unchanged)
        |
        v
AgentResponse returned (unchanged shape)
        |
        v
Frontend appends to its message list AND (new) the message/trace are
now independently retrievable via GET /api/chat/sessions/{id}/messages
after a refresh
```

Nothing about the Phase 7 request/response contract changes — `link` is
a new optional field, everything else is additive.

## 12. Error-handling strategy

Extends the existing, consistent pattern (`UploadValidationError`,
`VisualAnalysisError`, `HallucinationError` → controlled response, never
a bare 500 or a fabricated result) to every new endpoint:

- Unknown `session_id` / `analysis_id` / `chat_session_id` on a **read**
  endpoint → `404` with `{"code": "<x>_not_found", "message": "..."}`.
- A **write** endpoint given an unknown id where creation is the
  documented fallback (e.g. `chat_session_id` doesn't exist)
  → same behavior as today (Ph. 7 already creates fresh in that case);
  no change.
- §6c's injected linked-context never bypasses `app.agent.validation` —
  a stale/deleted linked record (`ON DELETE SET NULL` already prevents a
  dangling FK) simply means no injected context that turn, not an error.
- No new exception types needed beyond what §7's routers raise via
  `HTTPException` following the exact existing `UploadValidationError`
  pattern — no framework, no middleware change.
- Every failure mode gets a test asserting the response body contains no
  filesystem path, stack trace, SQL, or credential — mirroring
  `tests/agent/test_agent_api.py`'s existing
  `test_agent_chat_response_never_leaks_error_internals`.

## 13. Migration strategy

One Alembic revision (or two small sequential ones, TBD at
implementation time — likely one is cleaner):

1. `CREATE TABLE` for §6a's new table(s) (only if option (a) or (c) is
   approved — option (b) would still need the same table, just wired
   differently).
2. `ALTER TABLE chat_sessions ADD COLUMN ... NULL` ×4 (§6b), each with a
   `FOREIGN KEY ... ON DELETE SET NULL`.
3. No `ALTER` on any existing column; no data migration/backfill needed
   (all new columns nullable, all new tables empty at deploy time — this
   dev database has no real user data to preserve, and even production
   deployments of this pattern need no backfill since old rows simply
   have `NULL` linkage, which is exactly their correct historical state).
4. Verify with `alembic upgrade head` then `alembic check` (no new
   operations detected) against a real Postgres in Docker — same
   verification ritual used for every prior phase's migration.

No destructive operation anywhere in this plan.

## 14. Test strategy

New: `backend/tests/sessions/` (or `tests/test_sessions_api.py`, TBD to
match whether the existing convention is a subpackage or a flat file per
feature — `tests/agent/` is a subpackage, `tests/test_explanation_api.py`
is flat; will follow whichever the reviewer prefers, defaulting to a
subpackage since this phase adds enough surface to warrant one),
`backend/tests/test_analysis_retrieval.py`, `backend/tests/test_chat_history.py`,
plus extensions to `tests/agent/test_agent_api.py` for `link` and to
`tests/products`/`tests/routine`-adjacent files for the optional
`persist` field (exact placement depends on §6a's resolution).

Covers, at minimum, every case the Phase 8 prompt lists verbatim
(session create/retrieve/unknown/list-analyses/list-chats; analysis
upload-linked/retrieve/quality-rejected/no-visual-analysis-yet/completed/
unknown/repeated-retrieval/no-path-leakage; chat create/send/history/
multi-turn/persisted-messages/persisted-traces/unknown-session/
llm-failure/tool-failure/validation-failure), plus one integration test
exercising the full session → upload → quality → visual analysis → chat
session → question → tool call → deterministic result → explanation →
validation → persist → retrieve-history → retrieve-analysis chain, with
`FakeLLMProvider` (never a real key) and a real Postgres (matching every
existing DB-touching test in this repository).

All new tests must pass fresh against real Postgres in Docker, and the
DB-free subset (registry/tool/validation-style tests, if any new ones
are DB-free) must pass under `docker run --network none`, exactly as
Phase 6/7 did.

## 15. Backward compatibility considerations

- Every existing endpoint's request/response shape is either unchanged
  or extended with a new **optional** field with a safe default — no
  existing field renamed, removed, or made required.
- `frontend/src/lib/api.ts`'s existing exported functions keep their
  current signatures; new optional parameters are added, not required
  ones inserted.
- §6a is the one place this plan could reverse a previously-documented
  design decision (Phase 5's statelessness) — flagged explicitly for
  approval rather than assumed.
- `/results/[id]` changing from "always POST" to "GET first" is a
  behavior change but not a contract break: the POST endpoint, its
  status codes, and its response shape are all unchanged; only which
  endpoint the page calls when changes.
- No change to `docker-compose.yml`, environment variables, or the
  Docker image build process.

## 16. Security considerations

- `localStorage`-held `session_id`/`chat_session_id` are opaque UUIDs,
  never secrets — consistent with every other UUID already exposed
  throughout this app's API (product ids, analysis ids); this project
  has no auth model to weaken by that exposure.
- New GET endpoints never expose `ImageMetadata.storage_path` (already
  true for `ImageUploadResponse`, must remain true here) or any other
  filesystem path — enforced by using `ImageMetadataRead`, not the ORM
  model, in every new response, plus an explicit new test.
- No new secret, credential, or provider detail is ever persisted (§6c's
  injected context is domain JSON only, from tables that already
  contained no credentials).
- The tool registry's exact-name-only dispatch (Ph. 7) is untouched by
  this phase — §6c injects a *result*, never a tool *call*, so it cannot
  be used to smuggle an unregistered "tool" into the loop.
- No authentication is introduced, per explicit instruction — anyone who
  obtains a `session_id`/`analysis_id`/`chat_session_id` (e.g. via a
  shared link) can read that resource, identical to every existing
  UUID-addressable resource in this app today; documenting this
  consistently rather than silently changing the threat model for only
  the new endpoints.

## 17. Files to be created/modified (if approved)

**New:**
- `backend/app/api/sessions.py`, `backend/app/api/chat.py`
- `backend/app/schemas/session.py` (or extend `app/schemas/analysis.py`
  with `SessionAnalysesRead`/etc.)
- `backend/app/schemas/chat.py` (chat-history response shapes;
  `app/agent/schemas.py` stays owned by Ph. 7's live-chat contract)
- `backend/app/services/session_service.py` extensions (or a new
  `analysis_query_service.py`/`chat_query_service.py` for read-only
  query logic, keeping `session_service.py` focused on
  get-or-create as today)
- `backend/app/models/routine_analysis.py` and/or
  `comparison.py` (§6a, if approved)
- One new Alembic revision
- `backend/tests/test_sessions_api.py` (or `tests/sessions/`),
  `backend/tests/test_analysis_retrieval.py`,
  `backend/tests/test_chat_history.py`, `backend/tests/test_integration_phase8.py`
- `frontend/src/lib/session.ts`
- `docs/persistence.md`

**Modified:**
- `backend/app/models/chat.py` (§6b columns)
- `backend/app/models/__init__.py` (register new model(s))
- `backend/app/api/analysis.py` (`GET /{id}`)
- `backend/app/api/agent.py`, `app/agent/schemas.py`,
  `app/services/agent_service.py` (`link` field, §6c context injection)
- `backend/app/api/products.py`, `app/api/routine.py`,
  `app/schemas/product.py`, `app/schemas/routine.py` (§6a, if approved)
- `backend/app/services/vision_service.py` (§6d failure-state fix)
- `frontend/src/lib/api.ts`, `frontend/src/app/results/[id]/ResultsClient.tsx`,
  `frontend/src/app/chat/page.tsx`, possibly `/analyze`, `/routine`,
  `/compare` for `session_id` passthrough
- `README.md`, `docs/architecture.md`, `docs/api.md`, `docs/agent.md`,
  `docs/routine.md` (only if §6a option (b) is chosen)

---

## Decisions needed from you before implementation starts

1. **§6a**: (a) new separate persisting endpoints, (b) always-persist
   the existing endpoints, or (c) opt-in `persist` flag (recommended)?
2. Is the `GET /api/analysis/{id}` derived-status design in §10
   (deriving `quality_rejected`/`ready_for_visual_analysis` from
   existing fields rather than adding new stored enum values)
   acceptable, or would you prefer those as real stored `AnalysisStatus`
   values instead?
3. Any objection to the `ChatSession` linkage columns (§6b) as four
   separate nullable FKs, versus a single polymorphic
   `(linked_type, linked_id)` pair? (Four explicit FKs were chosen for
   real referential integrity — Postgres can enforce each one — at the
   cost of a column that's unused 3/4 of the time a chat is linked at
   all; a polymorphic pair is more compact but loses FK enforcement.)

Everything else in this plan is additive/low-risk and, if you'd rather
I just pick defaults for 1–3 and proceed, say so and I will use the
recommended option in each case.
