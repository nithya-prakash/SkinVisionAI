# API Reference

## Error response shape (Phase 10)

Every controlled error response — whether raised deliberately by a
router/service (a 404, a 422, a domain-specific 4xx) or an unexpected,
unhandled exception (a 500) — returns the same JSON shape:

```json
{ "detail": { "code": "some_stable_code", "message": "A human-readable description." } }
```

An unhandled exception (a bug, a DB failure) is caught by a global
handler (`app/main.py`) that logs the full exception server-side and
returns `{"detail": {"code": "internal_error", "message": "An
unexpected error occurred."}}` — never a stack trace, a filesystem path,
or any other internal detail. See [docs/safety.md](safety.md#global-error-handling).

## Implemented

### `GET /health` (Phase 1)

```json
{ "status": "ok", "app_name": "SkinVision AI", "environment": "development" }
```

No authentication. No database access. Used for container/infra health
checks.

### `POST /api/analysis/upload` (Phase 2)

Uploads an image and runs the non-diagnostic image quality gate
synchronously. `multipart/form-data` with:

- `file` (required) — a JPEG or PNG image
- `session_id` (optional) — an existing anonymous session id; if omitted
  or unknown, a new session is created

**Responses:**

| Status | When |
|---|---|
| `201` | Image accepted for processing — note this includes a *low-quality* image; `quality.is_acceptable` communicates that, not the HTTP status |
| `400` | Invalid or corrupted image content (fails Pillow decode, or claims to be an image but isn't) |
| `413` | Upload exceeds `IMAGE_MAX_SIZE_MB` |
| `415` | Unsupported format (claimed Content-Type or actual decoded format outside JPEG/PNG) |
| `422` | Missing `file` field |
| `429` | Rate limited — more than `RATE_LIMIT_UPLOAD_MAX_REQUESTS` (default 10) requests from this client IP within `RATE_LIMIT_UPLOAD_WINDOW_SECONDS` (default 60s); see [safety.md](safety.md#rate-limiting) |

**201 response body** (`app.schemas.image.ImageUploadResponse`):

```json
{
  "analysis_id": "…uuid…",
  "session_id": "…uuid…",
  "image": {
    "id": "…uuid…",
    "session_id": "…uuid…",
    "original_filename": "photo.jpg",
    "content_type": "image/jpeg",
    "size_bytes": 541255,
    "width_px": 800,
    "height_px": 800,
    "content_hash": "…sha256…",
    "quality_result": { "...": "same shape as quality below" },
    "created_at": "2026-09-08T10:59:38Z"
  },
  "quality": {
    "score": 0.91,
    "is_acceptable": true,
    "issues": [],
    "message": null,
    "metrics": {
      "width": 800, "height": 800, "aspect_ratio": 1.0,
      "file_size_bytes": 541255,
      "blur_score": 24762.45, "brightness_score": 128.0, "contrast_score": 35.1,
      "orientation": null
    }
  }
}
```

Never includes a server filesystem path. See
[docs/vision.md](vision.md) for the quality methodology and thresholds.

### `POST /api/analysis/{analysis_id}/visual-analysis` (Phase 3)

Runs the non-diagnostic visual-observation pipeline on a previously
uploaded image that passed the Phase 2 quality gate. No request body.

**Responses:**

| Status | Code | When |
|---|---|---|
| `200` | — | Structured `VisualAnalysisResult` (see below) |
| `404` | `analysis_not_found` | Unknown `analysis_id` |
| `404` | `image_not_found` / `image_file_missing` | Linked image row or file is missing |
| `422` | `quality_gate_not_passed` | Image never passed the Phase 2 quality gate |
| `409` | `image_not_retained` | Uploaded with `IMAGE_RETENTION_MODE=none`; nothing to analyze |

**200 response body** (`app.schemas.vision.VisualAnalysisResult`):

```json
{
  "analysis_id": "…uuid…",
  "image_id": "…uuid…",
  "observations": [
    {
      "feature": "redness",
      "level": "mild",
      "score": 0.31,
      "confidence": 0.74,
      "method": "lab_a_channel_mean",
      "note": "Estimated from color analysis, not tone-corrected; ..."
    }
  ],
  "region_used": "detected_face",
  "limitations": ["..."],
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "created_at": "2026-09-08T11:28:32Z"
}
```

Deterministic: calling this endpoint again for the same `analysis_id`
recomputes and returns byte-for-byte identical `score`/`level` values
(every algorithm involved is deterministic classical CV, no randomness).
See [docs/vision.md](vision.md) for the full feature methodology.

### `GET /api/analysis/{analysis_id}` (Phase 8)

Retrieves a previously created analysis -- **never recomputes** the
quality gate or the vision pipeline; reads back exactly what was already
persisted. See [docs/persistence.md](persistence.md#analysis-lifecycle).

**Responses:** `200` with `AnalysisDetailResponse`, or `404`
(`analysis_not_found`) for an unknown id.

**200 response body** (real output from a live run, before visual
analysis has been run):

```json
{
  "id": "…uuid…",
  "session_id": "…uuid…",
  "status": "ready_for_visual_analysis",
  "image": { "...": "same ImageMetadataRead shape as the upload response -- never a filesystem path" },
  "visual_analysis": null,
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "created_at": "2026-09-08T17:30:55Z",
  "updated_at": "2026-09-08T17:30:55Z"
}
```

`status` is one of `quality_rejected`, `ready_for_visual_analysis`,
`analyzing`, `completed`, `failed` -- derived from the stored analysis
status plus the image's already-computed quality result, not a
fabricated guess. `visual_analysis` (the same `VisualAnalysisResult`
shape the POST endpoint above returns) is `null` until `status` is
`"completed"`.

### `POST /api/products/analyze` (Phase 4)

Parses a product's raw ingredient text, normalizes each token against the
versioned rule set, and runs the deterministic compatibility engine — no
LLM call, no network call, fully offline and deterministic. Always
returns 201; an unknown ingredient or an absent rule for a pair is a
normal, informative result, never an error.

**Request body** (`app.schemas.product.ProductAnalyzeRequest`):

```json
{
  "session_id": null,
  "name": "Retinol Serum",
  "category": null,
  "raw_ingredient_text": "Retinol, Glycolic Acid"
}
```

**Responses:**

| Status | When |
|---|---|
| `201` | Structured `ProductAnalyzeResponse` (see below) |
| `422` | Missing/empty `name` or `raw_ingredient_text`, or an unsupported `category` |

**201 response body** (`app.schemas.product.ProductAnalyzeResponse`):

```json
{
  "product_id": "…uuid…",
  "session_id": "…uuid…",
  "name": "Retinol Serum",
  "category": null,
  "compatibility": {
    "ingredients": [
      { "raw_text": "Retinol", "normalized_name": "retinol", "matched": true, "ambiguous": false, "candidates": [], "categories": ["retinoid"] },
      { "raw_text": "Glycolic Acid", "normalized_name": "glycolic_acid", "matched": true, "ambiguous": false, "candidates": [], "categories": ["aha", "exfoliant"] }
    ],
    "interactions": [
      {
        "rule_id": "retinol_glycolic_acid_caution",
        "ingredient_a": "retinol",
        "ingredient_b": "glycolic_acid",
        "severity": "caution",
        "message": "Combining retinol with glycolic acid may increase irritation. ...",
        "reason": "Both retinol and glycolic acid (an AHA) can irritate skin on their own; ...",
        "source": "Cleveland Clinic",
        "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol",
        "last_verified": "2026-09-08"
      }
    ],
    "unknown_ingredients": [],
    "limitations": ["..."],
    "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice."
  }
}
```

(Real output from a live run against the actual API — not fabricated.)
Deterministic: the same ingredient text always produces byte-for-byte
identical output. See [docs/ingredients.md](ingredients.md) for the full
severity model, source policy, and rule-authoring workflow.

### `POST /api/routine/analyze` (Phase 5)

Analyzes a set of products as a routine: per-product normalized
ingredients, overlapping actives across products, cross-product
compatibility (Phase 4's engine reused, not duplicated), and a suggested
AM/PM order. **Stateless by default — nothing is persisted.** No LLM
call, no network call. Phase 8 adds an opt-in `persist` field (see
[docs/persistence.md](persistence.md)); the default (`false`) behavior
is byte-for-byte identical to Phase 5.

**Request body** (`app.schemas.routine.RoutineAnalysisRequest`):

```json
{
  "products": [
    { "product_name": "Cleanser", "raw_ingredients": "Water, Glycerin", "category": "cleanser", "time_of_day": "AM_AND_PM" },
    { "product_name": "Retinol Serum", "raw_ingredients": "Retinol", "category": "treatment", "time_of_day": "PM" },
    { "product_name": "Acid Toner", "raw_ingredients": "Glycolic Acid", "category": "toner", "time_of_day": "PM" },
    { "product_name": "Sunscreen", "raw_ingredients": "Zinc Oxide", "category": "sunscreen" }
  ],
  "session_id": null,
  "persist": false
}
```

`time_of_day` is one of `AM`, `PM`, `AM_AND_PM`, or `unspecified`
(default). `category` is optional; omitted means "unknown," never
guessed. `session_id` is only used when `persist: true` (attaches the
saved record to an existing session; omit to create a new one).

**Responses:** `200` with a structured `RoutineAnalysisResult`, or `422`
for an empty `products` list or a product missing `raw_ingredients`.

**200 response body** (abridged; real output from a live run):

```json
{
  "products": [ "...per-product normalized ingredients..." ],
  "overlapping_actives": [],
  "interactions": [
    {
      "rule_id": "retinol_glycolic_acid_caution",
      "ingredient_a": "retinol", "ingredient_b": "glycolic_acid",
      "severity": "caution", "message": "...", "source": "Cleveland Clinic",
      "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol",
      "products": ["Acid Toner", "Retinol Serum"]
    }
  ],
  "suggested_am": [
    { "product_name": "Cleanser", "category": "cleanser", "step_order": 0 },
    { "product_name": "Sunscreen", "category": "sunscreen", "step_order": 4 }
  ],
  "suggested_pm": [
    { "product_name": "Cleanser", "category": "cleanser", "step_order": 0 },
    { "product_name": "Acid Toner", "category": "toner", "step_order": 1 },
    { "product_name": "Retinol Serum", "category": "treatment", "step_order": 2 }
  ],
  "unscheduled_products": [],
  "limitations": ["..."],
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "id": null
}
```

`id` is `null` unless the request had `persist: true`, in which case it
is the new `RoutineAnalysisRecord`'s id. Deterministic. See
[docs/routine.md](routine.md) for the ordering methodology, overlap
detection, and how cross-product compatibility reuses Phase 4 without
duplicating it.

### `POST /api/products/compare` (Phase 5)

Deterministically compares two products: shared/unique ingredients,
shared active categories, and any compatibility interactions between
them (Phase 4's engine reused, not duplicated). **Stateless by
default.** Never computes an overall "better product" score. Phase 8
adds the same opt-in `persist` field as `/api/routine/analyze` above.

**Request body** (`app.schemas.product.ProductCompareRequest`):

```json
{
  "product_a": { "name": "Product A", "raw_ingredient_text": "Retinol, Niacinamide, Glycerin" },
  "product_b": { "name": "Product B", "raw_ingredient_text": "Retinol, Salicylic Acid, Glycerin" },
  "session_id": null,
  "persist": false
}
```

**Responses:** `200` with a structured `ProductComparisonResult`, or
`422` for missing/empty ingredient text.

**200 response body** (real output from a live run):

```json
{
  "product_a_name": "Product A",
  "product_b_name": "Product B",
  "shared_ingredients": ["glycerin", "retinol"],
  "only_in_a": ["niacinamide"],
  "only_in_b": ["salicylic_acid"],
  "shared_categories": ["humectant", "retinoid"],
  "interactions": [
    { "rule_id": "retinol_niacinamide_informational", "severity": "informational", "...": "..." },
    { "rule_id": "retinol_salicylic_acid_caution", "severity": "caution", "...": "..." }
  ],
  "unknown_ingredients_a": [],
  "unknown_ingredients_b": [],
  "limitations": ["..."],
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "id": null
}
```

`id` is `null` unless `persist: true`, in which case it is the new
`ComparisonRecord`'s id. Deterministic. See [docs/routine.md](routine.md).

## LLM explanations (Phase 6)

Three endpoints, one per Phase 4/5 analysis shape. Each takes the exact
same request body as its deterministic-only sibling above, re-runs that
same computation itself server-side (the frontend cannot submit
pre-computed facts for the LLM to "explain"), and additionally attaches
an AI-generated narrative explanation. **Stateless by default** — the
initial Phase 6 migration check found no schema change needed. Since
`/compare` and `/routine` here reuse the exact same
`ProductCompareRequest`/`RoutineAnalysisRequest` schemas as their
deterministic-only siblings, Phase 8's opt-in `persist` field works
here too — set it and `analysis.id` (nested one level deeper than the
raw endpoints' top-level `id`) is populated the same way. No LLM call is
ever made by, or exposes a key to, the frontend — see [docs/llm.md](llm.md).

The deterministic `analysis` is always present, even when the LLM call
fails entirely — these endpoints always return `200`; a failed or
rejected explanation is communicated via `explanation_status`, never by
withholding the analysis.

### `POST /api/explanations/product`

Same request body as `POST /api/products/analyze`. Response
(`app.schemas.explanation.ProductExplanationResponse`):

```json
{
  "analysis": { "...": "same shape as /api/products/analyze's compatibility field" },
  "explanation": {
    "summary": "This is a deterministic, rule-based summary: 1 documented ingredient interaction(s) were found.",
    "key_points": ["1 documented ingredient interaction(s) were found."],
    "interactions_explained": [
      {
        "rule_id": "retinol_glycolic_acid_caution",
        "ingredient_a": "retinol", "ingredient_b": "glycolic_acid",
        "severity": "caution",
        "message": "Combining retinol with glycolic acid may increase irritation. ...",
        "source": "Cleveland Clinic",
        "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol",
        "explanation": "A documented interaction was found between retinol and glycolic_acid."
      }
    ],
    "overlap_explained": [],
    "routine_notes": [],
    "limitations": ["..."],
    "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice."
  },
  "explanation_status": "available",
  "explanation_error": null
}
```

(Real output from a live run against the fake provider — not fabricated;
`severity`/`source`/`source_url` are copied verbatim from `analysis`,
never supplied by the LLM.)

### `POST /api/explanations/compare`

Same request body as `POST /api/products/compare`. Response
(`app.schemas.explanation.ComparisonExplanationResponse`): same envelope
shape, `analysis` is a `ProductComparisonResult`.

### `POST /api/explanations/routine`

Same request body as `POST /api/routine/analyze`. Response
(`app.schemas.explanation.RoutineExplanationResponse`): same envelope
shape, `analysis` is a `RoutineAnalysisResult`, and `explanation.routine_notes`
may be populated.

**Responses (all three):** `200` with the envelope above (whether or not
the AI explanation succeeded), or `422` for the same validation failures
as the underlying deterministic endpoint (invalid request body — checked
before any LLM call is attempted).

**When the LLM is unavailable or its output fails validation** (missing
`LLM_API_KEY`, provider timeout/rate-limit/auth failure, malformed
response, or a hallucination rejected by `app.llm.validation`):

```json
{
  "analysis": { "...": "full deterministic result, unaffected" },
  "explanation": null,
  "explanation_status": "unavailable",
  "explanation_error": "AI explanation is currently unavailable (provider authentication issue)."
}
```

`explanation_error` is always one of a small set of generic, user-safe
strings — never the raw provider exception, and never an API key or
request internals.

## Agent chat (Phase 7)

### `POST /api/agent/chat`

Runs one bounded agent turn: the model may call any of the 5 registered
deterministic tools (see [docs/agent.md](agent.md)) before producing a
final answer, which is validated against everything those tool calls
actually returned. **Persists** the chat session/message/tool trace
(`ChatSession`/`ChatMessage`/`AgentTrace`, Phase 1 models, previously
unused) — unlike the stateless Phase 5/6 endpoints above, this one is
stateful by design so a conversation can be continued.

**Request body** (`app.agent.schemas.AgentChatRequest`):

```json
{
  "message": "Can I use retinol and salicylic acid together?",
  "session_id": null,
  "chat_session_id": null,
  "context": null,
  "link": null
}
```

`session_id`/`chat_session_id` are optional (omit both to start a fresh
anonymous session and a fresh conversation; pass back the
`chat_session_id` from a prior response to continue it — see
docs/agent.md's conversational-memory section for exactly what "continue"
means here). `context` is optional, client-supplied, plain data — like
`message`, always untrusted; it cannot make the agent skip calling a tool
to ground a fact.

`link` (Phase 8, optional) attaches this chat session to one existing
analysis/product/routine-record/comparison-record, so the agent receives
it as trusted context without a real tool call — exactly one of its four
fields must be set:

```json
{ "link": { "product_id": "…uuid…" } }
```

Only applied when this request creates a *new* chat session; ignored
when continuing an existing one. An id that doesn't exist is a
controlled `400` (`invalid_chat_link`), not silently ignored. See
[docs/agent.md](agent.md#failure-behavior) and
[docs/persistence.md](persistence.md#chat-lifecycle).

**Responses:** `200` with a structured `AgentResponse`
(`app.agent.schemas.AgentResponse`) for every outcome of the agent turn
itself — including an LLM failure, a rejected/hallucinating answer, or a
hit tool-call/turn limit, communicated via the body's `status`/`error`
fields, never a bare 5xx. Only three things short-circuit before the
agent loop even runs: `422` for an empty/oversized `message`, `400`
(`invalid_chat_link`) for a `link` naming an id that doesn't exist, and
`429` (`rate_limited`) — more than `RATE_LIMIT_AGENT_CHAT_MAX_REQUESTS`
(default 20) requests from this client IP within
`RATE_LIMIT_AGENT_CHAT_WINDOW_SECONDS` (default 60s); see
[safety.md](safety.md#rate-limiting).

**200 response body** (real output from a live run against the fake
provider — not fabricated):

```json
{
  "answer": "retinol and salicylic acid have a documented caution-level interaction.",
  "tool_trace": [
    {
      "tool_name": "check_ingredient_compatibility",
      "arguments": { "ingredients": ["retinol", "salicylic_acid"] },
      "result": {
        "interactions": [
          {
            "rule_id": "retinol_salicylic_acid_caution",
            "ingredient_a": "retinol", "ingredient_b": "salicylic_acid",
            "severity": "caution", "message": "...",
            "source": "Cleveland Clinic",
            "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol"
          }
        ],
        "...": "full CompatibilityResult"
      },
      "call_index": 0,
      "success": true,
      "error": null
    }
  ],
  "citations": [
    { "source": "Cleveland Clinic", "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol" }
  ],
  "limitations": ["..."],
  "disclaimer": "SkinVision AI provides educational skincare insights, not medical diagnosis or medical advice.",
  "status": "success",
  "chat_session_id": "…uuid…",
  "message_id": "…uuid…"
}
```

**When the LLM is unavailable, a tool call fails, the answer fails
validation, or a loop limit is hit** (`status` one of `tool_error`,
`llm_unavailable`, `validation_error`, `max_tool_calls`): `answer` is
typically empty and any partial `tool_trace` collected so far is still
returned — the deterministic facts gathered before the failure are never
discarded. See [docs/agent.md](agent.md#failure-behavior) for the full
table of failure modes.

## Sessions (Phase 8; Phase 9 adds products/routine-analyses/comparisons)

Application-level session retrieval — separate from
`get_or_create_session`'s existing implicit write-path behavior used by
every other endpoint above. See [docs/persistence.md](persistence.md).

### `POST /api/sessions`

Creates a new anonymous session explicitly. Response
(`app.schemas.analysis.SessionRead`): `{"id": "…uuid…", "created_at": "…"}`.

### `GET /api/sessions/{session_id}`

Session metadata. `404` (`session_not_found`) for an unknown id — a read
endpoint naming a specific id never silently creates a new, unrelated
session (unlike write paths).

### `GET /api/sessions/{session_id}/analyses`

This session's `SkinAnalysis` rows, newest first, each summarized with
its derived client-facing status (see `GET /api/analysis/{id}` above).
`404` for an unknown session id.

```json
{
  "session_id": "…uuid…",
  "analyses": [
    { "id": "…uuid…", "status": "completed", "created_at": "…" }
  ]
}
```

### `GET /api/sessions/{session_id}/chats`

This session's `ChatSession` rows, newest first, each with its message
count. `404` for an unknown session id.

```json
{
  "session_id": "…uuid…",
  "chats": [
    { "id": "…uuid…", "message_count": 2, "created_at": "…", "updated_at": "…" }
  ]
}
```

### `GET /api/sessions/{session_id}/products` (Phase 9)

This session's single-product ingredient analyses (Phase 4 `Product`
rows), newest first — counts derived at query time from the
already-persisted `analysis_result`, never recomputed. `404` for an
unknown session id.

```json
{
  "session_id": "…uuid…",
  "products": [
    { "id": "…uuid…", "name": "Retinol Serum", "category": null, "interaction_count": 1, "unknown_ingredient_count": 0, "created_at": "…" }
  ]
}
```

### `GET /api/sessions/{session_id}/routine-analyses` (Phase 9)

This session's **opt-in-persisted** routine analyses (`RoutineAnalysisRecord`,
Phase 8) — only those saved with `persist: true` on
`POST /api/routine/analyze` appear here. `404` for an unknown session id.

```json
{
  "session_id": "…uuid…",
  "routine_analyses": [
    { "id": "…uuid…", "product_count": 2, "interaction_count": 1, "created_at": "…" }
  ]
}
```

### `GET /api/sessions/{session_id}/comparisons` (Phase 9)

This session's **opt-in-persisted** product comparisons (`ComparisonRecord`,
Phase 8) — only those saved with `persist: true` on
`POST /api/products/compare` appear here. `404` for an unknown session id.

```json
{
  "session_id": "…uuid…",
  "comparisons": [
    { "id": "…uuid…", "product_a_name": "Product A", "product_b_name": "Product B", "interaction_count": 1, "created_at": "…" }
  ]
}
```

## Chat history (Phase 8)

Read-only retrieval, distinct from `POST /api/agent/chat` (the live
turn, above) — reload a conversation after a refresh instead of losing
it, since it was always persisted server-side.

### `GET /api/chat/sessions/{chat_session_id}`

One chat session's metadata, including its optional linked-context
reference (`app.schemas.chat.ChatSessionRead`):

```json
{
  "id": "…uuid…", "session_id": "…uuid…",
  "skin_analysis_id": null, "product_id": "…uuid…",
  "routine_analysis_id": null, "comparison_id": null,
  "created_at": "…", "updated_at": "…"
}
```

`404` (`chat_session_not_found`) for an unknown id.

### `GET /api/chat/sessions/{chat_session_id}/messages`

Every message in the session, chronological, each assistant message's
`tool_trace` reconstructed from its persisted `AgentTrace` rows — exactly
the same safe shape `POST /api/agent/chat` already returns live, so a
reloaded conversation looks identical to one still in memory. `404` for
an unknown id.

```json
{
  "chat_session_id": "…uuid…",
  "messages": [
    { "id": "…uuid…", "chat_session_id": "…uuid…", "role": "user", "content": "...", "tool_trace": [], "created_at": "…" },
    { "id": "…uuid…", "chat_session_id": "…uuid…", "role": "assistant", "content": "...", "tool_trace": [ "...same shape as POST /api/agent/chat's tool_trace..." ], "created_at": "…" }
  ]
}
```

Never includes hidden reasoning or a system prompt — only what
`POST /api/agent/chat` already exposes live.

## Planned (later phases)

All endpoints use dedicated Pydantic request/response schemas — SQLAlchemy
models are never exposed directly. Anonymous session-based usage only, no
user accounts.

| Endpoint | Phase | Purpose |
|---|---|---|
| `POST /api/routine` | future | Create/persist a user-curated AM/PM routine from existing `Product` rows (`Routine`/`RoutineItem`, Phase 1 models, still unused) — distinct from the stateless `/api/routine/analyze` above and from Phase 8's `RoutineAnalysisRecord` (a saved *analysis result*, not an editable routine) |

## Schema contracts defined ahead of their endpoints

- `app.schemas.routine` — `RoutineCreate/Read`, `RoutineItemCreate/Read` (persisted-routine CRUD, still unused -- distinct from the Phase 5 analysis schemas and the Phase 8 `RoutineAnalysisRecord` in the same file)
- `app.schemas.analysis` — `SkinAnalysisCreate/Read` (still unused; `SessionRead` in the same module is used by `/api/sessions` since Phase 8)

See each module's docstrings for field-level detail; OpenAPI docs are
auto-generated by FastAPI at `/docs` once more routers are registered.
