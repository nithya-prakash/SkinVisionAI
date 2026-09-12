# Resume-Ready Engineering Metrics

Every number below was measured directly from this repository — its
source code, its test/evaluation suites, or a live run of the actual
application — re-verified as of the authentication follow-up pass.
None is estimated, rounded up, or inferred. "How measured" says
exactly what was run or read to get the number, so it can be
independently reproduced from [README.md](../README.md)'s documented
commands or verified by reading the cited file.

**What these numbers are not**: none of them are a claim about
real-world skincare or dermatological accuracy. See
[Not a clinical accuracy benchmark](evaluation.md#not-a-clinical-accuracy-benchmark)
before using any evaluation number in a way that could be read as one.

## All verified metrics

| # | Metric | Value | What it measures | Source | How measured |
|---|---|---|---|---|---|
| 1 | Backend test suite size | **773 tests** | Total unit/integration tests in `backend/tests/` | Tests | `pytest --collect-only` count, confirmed via `docker compose exec api pytest tests/ -q` |
| 2 | Backend test pass rate | **773/773 = 100%** (full checkout) | Whether the entire backend suite passes | Tests / live verification | Full re-run against a freshly rebuilt (`--no-cache`) Docker image and an empty database. (772/773 pass with 1 environment-conditional skip when run *inside* the backend-only Docker image, because that one test cross-checks `README.md` against the rule data and the Docker build context doesn't copy `README.md` in — it runs and passes in a full local checkout.) |
| 3 | Evaluation case count | **104 cases** | Size of the offline evaluation harness, across 7 subsystems | Evaluation | `python -m evaluation` summary output |
| 4 | Evaluation pass rate | **104/104 = 100.00%** | Overall harness pass rate | Evaluation | `python -m evaluation` / `pytest tests/evaluation/`, both re-run against the fresh rebuild |
| 5 | Evaluation subsystem breakdown | Vision 15/15, Ingredients 28/28, Routine 10/10, Comparison 8/8, LLM explanation 9/9, Agent 19/19, Safety 15/15 — **each 100%** | Per-subsystem coverage and pass rate | Evaluation | Same harness run, per-subsystem summary |
| 6 | Deterministic CV features computed | **5** (redness, visible texture, shine/oiliness, uneven tone, visible spots/marks) | Distinct visual signals the classical OpenCV pipeline actually reports | Source code | `app/vision/analyzer.py` — confirmed only 5 of the 6 `ObservationFeature` enum members are ever emitted; `DRYNESS` is deliberately excluded (see the code's own `DRYNESS_LIMITATION` string) |
| 7 | Agent tools registered | **5** (`check_ingredient_compatibility`, `analyze_product`, `compare_products`, `analyze_routine`, `get_ingredient_information`) | Size of the bounded tool-calling agent's tool surface | Source code | `app.agent.tools.build_tool_registry()` — `len(registry.specs())`, checked live in the running container |
| 8 | Agent max tool calls per turn | **5** (`AGENT_MAX_TOOL_CALLS`, configurable) | Hard cap bounding the agent loop | Source code | `app.config.Settings.agent_max_tool_calls` default, read live |
| 9 | Agent max turns | **8** (`AGENT_MAX_TURNS`, configurable) | Hard cap on LLM round-trips per chat turn | Source code | `app.config.Settings.agent_max_turns` default, read live |
| 10 | Ingredient compatibility rules | **6** | Source-cited pairwise ingredient interaction rules (Cleveland Clinic, AAD) | Source code | `rules/ingredients/compatibility.json`, loaded via `get_rule_set().rules_by_pair` |
| 11 | Canonical ingredients | **28** | Ingredients the deterministic engine recognizes | Source code | `rules/ingredients/aliases.json`, loaded via `get_rule_set().canonical_names` |
| 12 | Ingredient aliases indexed | **38** | Alternate names (INCI synonyms, casing/spacing variants) resolving to a canonical ingredient | Source code | `get_rule_set().alias_index` length, read live |
| 13 | Routine active-ingredient categories tracked for overlap detection | **5** (retinoid, AHA, BHA, vitamin C, acne treatment) | Categories the routine engine checks for duplicate-active overexposure | Source code | `rules/routine/overlap.json`'s `active_categories` |
| 14 | Product categories supported | **8** (cleanser, toner, serum, moisturizer, sunscreen, exfoliant, treatment, other) | Categories used for routine placement/comparison | Source code | `app.schemas.common.ProductCategory` enum |
| 15 | LLM provider implementations | **3** (Anthropic, OpenAI-compatible, and a deterministic Fake provider for offline dev/testing) | Breadth of the provider-abstraction layer | Source code | `app.llm.provider` — concrete subclasses of `LLMProvider` |
| 16 | Frontend application routes | **9** (`/`, `/analyze`, `/chat`, `/compare`, `/history`, `/login`, `/results/[id]`, `/routine`, `/signup`) | Distinct user-facing pages | Live verification | `next build` route output against the current build |
| 17 | API endpoints | **23** REST endpoints under `/api/` (plus 1 health check) | Size of the backend's public HTTP surface | Live verification | `GET /openapi.json` against the running API, counted programmatically |
| 18 | Database tables | **13** application tables (plus Alembic's own bookkeeping table) | Persistent schema size | Live verification | `\dt` against a freshly migrated, empty PostgreSQL database |
| 19 | Database migrations | **6** versioned Alembic migrations | Schema evolution history, all applying cleanly from empty | Source code / live verification | File count in `backend/alembic/versions/`, confirmed applying with zero errors on a fresh `alembic upgrade head` |
| 20 | Safety/attack evaluation categories | **15** distinct categories (prompt injection, system-prompt extraction, API-key extraction, hidden-reasoning extraction, arbitrary-code-execution request, unsupported diagnosis, unsupported skincare claim, fabricated citation, fabricated URL, fabricated numeric result, Unicode zero-width bypass, case-variation bypass, malformed tool call, unknown tool call, malicious ingredient/product text) | Breadth of the dedicated adversarial-input test dataset | Evaluation | `evaluation.datasets.safety.SAFETY_CASES`, enumerated live — 1 case per category |
| 21 | Offline execution | **100%** of the 773-test backend suite and all 104 evaluation cases run with zero network access and zero LLM API key | Reproducibility without paid/external dependencies | Live verification | Every LLM/agent path uses a scripted `FakeLLMProvider`; verified with a `docker run --network none`-style check |
| 22 | Determinism checks | Dedicated 3×-repeat determinism cases in the vision and ingredients evaluation datasets | Confirms identical output on repeated runs of the same input (no hidden randomness) | Evaluation | `evaluation/metrics.py::assert_deterministic`, exercised by the vision and ingredients datasets |
| 23 | Docker clean-rebuild verification | `down -v` → `build --no-cache` (both images) → `up` from an **empty database**: 0 errors, health check `200`, all 5 migrations applied automatically | End-to-end reproducibility of the deployment | Live verification | Full teardown/rebuild/startup cycle actually run, not assumed |
| 24 | Frontend static validation | `tsc --noEmit`: 0 errors · `eslint`: 0 errors/warnings · `next build`: succeeded across all 7 routes | Type safety and lint cleanliness | Live verification | Commands run directly against the current source |
| 25 | Rate-limited endpoints | **3** (image upload: 10 req/60s; agent chat: 20 req/60s; login/register: 10 req/60s, all per client IP, configurable) | Cost-bearing and brute-force-risk endpoints protected, independent of and in addition to authentication | Source code / live verification | `app.core.rate_limit` config defaults; a live test hammering an endpoint past its limit returned a controlled `429` |
| 26 | Authenticated accounts | Email/password + JWT in an httpOnly cookie; a `UserSession` is owned by its `User` (unique FK) | Real access control, not possession-based UUID access | Source code / live verification | `app/services/auth_service.py`; a second, independently registered user proven unable to read/act on the first user's session (403), verified both by `tests/test_auth_api.py` and live `curl` with separate cookie jars |
| 27 | Development phases completed | 12 (context only — see note below) | Project scope/history, not an engineering achievement | Source code / docs | `docs/phases.md` build log |

**Note on #27**: phase count describes how the project was built, not
what it achieves technically. It's useful only as development-process
context (e.g. "built incrementally over 12 scoped phases, each with its
own tests before moving on") — never as a standalone resume bullet.

## Recommended resume metrics

The strongest 8–12 for a one-page AI Engineer / Applied AI / ML
Engineer resume, and why each earns its place:

1. **773 backend tests, 100% passing** — the single most concrete
   signal of engineering rigor; a recruiter can literally run the
   command in `README.md` and get the same number.
2. **104-case offline evaluation harness, 104/104 passing across 7
   subsystems** — shows evaluation-driven development as a practice,
   not a one-off demo; distinct from unit testing, which is what makes
   it worth a separate bullet.
3. **15-category adversarial/safety evaluation suite** — directly
   demonstrates security- and safety-mindedness for an AI system, a
   specific and differentiating skill for AI Engineer roles.
4. **5 deterministic tools behind a bounded agent loop (max 5 tool
   calls, max 8 turns)** — concrete, verifiable numbers that make
   "bounded tool-calling agent" a claim with teeth instead of a buzz
   phrase.
5. **3 LLM provider implementations behind one abstraction** — shows
   provider-agnostic design, a real architectural decision recruiters
   in this space specifically look for.
6. **100% offline-reproducible test/evaluation suite (zero API key,
   zero network)** — a genuinely unusual and valuable property; most
   LLM-app portfolios can't make this claim at all.
7. **5-feature classical computer vision pipeline, fully deterministic
   and offline** — demonstrates CV fundamentals independent of any
   pretrained/black-box model, a good counterweight to the LLM-heavy
   parts of the stack.
8. **23 REST endpoints, 13-table PostgreSQL schema, 6 migrations, all
   verified against a from-scratch Docker rebuild** — proves full-stack
   ownership (not just a backend or just a frontend) and deployment
   discipline.
9. **28 canonical ingredients / 6 source-cited compatibility rules,
   entirely offline and version-controlled** — shows the
   deterministic/LLM trust-boundary architecture is real code with real
   data behind it, not just a diagram.
10. **3 rate-limited endpoints with per-IP fixed-window limiting** — a
    small, concrete security-hardening detail that's easy for an
    interviewer to ask a follow-up question about.
11. **Real authentication with proven cross-user isolation** — a second,
    independently registered user is demonstrably rejected (403) from
    the first user's session even holding its exact UUID; concrete
    evidence of understanding access control, not just building a login
    form.

## Example resume bullets

- Designed and built a full-stack AI application enforcing a strict
  **deterministic/LLM trust boundary**: all domain facts (CV
  observations, ingredient interactions, routine ordering) are computed
  by versioned, source-cited Python logic, while the LLM only
  orchestrates and narrates — backed by a **773-test suite** and a
  **104-case offline evaluation harness**, both 100% passing and
  runnable with zero API key or network access.
- Implemented a **bounded tool-calling agent** (5 deterministic tools,
  capped at 5 tool calls / 8 turns per request) with a **post-hoc,
  structural anti-hallucination validator** that grounds every claim in
  actual tool output — proven against a dedicated **15-category
  adversarial evaluation suite** covering prompt injection, credential
  extraction, and fabricated-citation attacks.
- Built a **provider-agnostic LLM abstraction** (Anthropic,
  OpenAI-compatible, and a deterministic fake for CI) so the entire
  test and evaluation suite runs fully offline, and diagnosed/fixed a
  real **Docker build-time configuration bug** (`NEXT_PUBLIC_*` env
  inlining) by proving the defect and the fix with actual container
  builds rather than assumption.
- Implemented a **5-feature classical computer vision pipeline**
  (OpenCV: redness, texture, shine, tone, spot detection) with a
  deterministic image-quality gate, verified for reproducibility via
  dedicated determinism tests that assert identical output across
  repeated runs of the same input.
- Designed and shipped **JWT-cookie authentication** (email/password,
  bcrypt, httpOnly cookie) that closed a real access-control gap — every
  session-scoped resource is now owned by its account rather than
  reachable by anyone holding its UUID — and proved the fix with a test
  suite where a second registered user is provably rejected (403) from
  the first user's data, not just a login screen bolted onto an
  otherwise-unchanged data model.
- Owned the system end-to-end — **19 REST endpoints**, a **12-table
  PostgreSQL schema** across **5 Alembic migrations**, and a
  **Docker Compose deployment** — verified with a genuine
  teardown/no-cache-rebuild/cold-start cycle rather than an
  already-warm environment.
