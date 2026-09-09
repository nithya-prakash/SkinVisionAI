# Project history

SkinVision AI was built in 12 phases. This log records what each phase
delivered — kept out of the main [README](../README.md) to keep that
readable, but preserved here for anyone who wants the build history.

- **Phase 1** — repository scaffold, backend skeleton (FastAPI, Pydantic v2
  schemas, SQLAlchemy models, Alembic), frontend skeleton
  (Next.js/TypeScript/Tailwind), Docker Compose, initial docs.
- **Phase 2** — image ingestion (`POST /api/analysis/upload`) and the
  non-diagnostic image quality gate (OpenCV/Pillow: resolution, blur,
  brightness, contrast), with configurable thresholds and retention, real
  database persistence, and a working `/analyze` upload UI.
- **Phase 3** — non-diagnostic visual-observation pipeline
  (`POST /api/analysis/{id}/visual-analysis`): classical OpenCV feature
  extraction (redness, visible texture, shine, uneven tone, visible
  spots/marks) over a face-or-fallback region of interest, with
  configurable thresholds, deterministic/reproducible output, and a
  `/results/[id]` page displaying the results.
- **Phase 4** — deterministic ingredient parser, normalizer, and
  compatibility engine (`POST /api/products/analyze`): 27 canonical
  ingredients, 6 source-cited rules (Cleveland Clinic, American Academy
  of Dermatology), ambiguous-alias handling, reverse-order/duplicate-safe
  compatibility checking, zero network/LLM dependency (verified with
  `docker run --network none`), and an `/compare` page for single-product
  ingredient analysis.
- **Phase 5** — routine intelligence built on the Phase 4 engine, with zero
  duplicated rule logic: `POST /api/routine/analyze` (overlapping actives
  across products, cross-product compatibility, deterministic AM/PM
  ordering with a documented sunscreen-final-AM exception) and
  `POST /api/products/compare` (shared/unique ingredients, shared active
  categories, interactions — no "better product" score). Both endpoints
  are stateless (no migration needed). A `/routine` builder page and a
  two-mode `/compare` page (single-product analysis / two-product
  comparison).
- **Phase 6** — LLM provider abstraction (`LLMProvider`, Anthropic +
  OpenAI-compatible + a deterministic fake for tests/offline dev) and a
  structured AI explanation layer on top of Phases 4/5:
  `POST /api/explanations/{product,compare,routine}`. The LLM explains
  the deterministic result in plain language and can never alter it —
  its output schema has no severity/citation fields, and every response
  passes an anti-hallucination validator before reaching a user. The
  deterministic analysis is always returned, even when the LLM call
  fails. Stateless (no migration). Zero API-key/network dependency in
  tests, verified with `docker run --network none`. `/routine` and
  `/compare` now show an "AI Explanation" section, visually distinct
  from the deterministic results above it, with a clear
  "unavailable" fallback state. See [docs/llm.md](llm.md).
- **Phase 7** — a small, custom agentic tool-calling layer (no LangChain/
  LangGraph/agent framework): `POST /api/agent/chat` lets the LLM choose
  among 5 deterministic tools (each a thin wrapper around an existing
  Phase 4/5 engine call — `check_ingredient_compatibility`,
  `analyze_product`, `compare_products`, `analyze_routine`,
  `get_ingredient_information`), read their structured results, and
  produce a final answer grounded exclusively in what those tools
  returned. The LLM decides *which tool to call*, never *whether an
  ingredient combination is safe* — enforced structurally (its raw
  final-answer schema has no severity/citation field) and by a
  trace-grounded anti-hallucination validator reused from Phase 6. No
  arbitrary code execution: a tool call is an exact-string lookup into a
  pre-registered registry, never `eval`/`exec`/dynamic import. Bounded
  (`AGENT_MAX_TOOL_CALLS=5`, `AGENT_MAX_TURNS=8`), deduplicated, and
  fails safely (an LLM failure, a rejected answer, or a hit limit always
  returns a controlled response with whatever tool trace was collected).
  One migration (`agent_traces` gained `success`/`error_message`
  columns); reuses the Phase 1 `ChatSession`/`ChatMessage`/`AgentTrace`
  models, previously defined but unused. A real `/chat` page replaces
  the placeholder, showing an expandable "How SkinVision AI reached this
  answer" trace. See [docs/agent.md](agent.md).
- **Phase 8** — application integration & persistence: a real application
  session (`POST /api/sessions`, persisted client-side in `localStorage`)
  replaces the previous implicit-and-immediately-orphaned session
  created on almost every request. `GET /api/analysis/{id}` retrieves a
  previously created analysis instead of recomputing it (`/results/[id]`
  now fetches on load and only re-runs the vision pipeline on an
  explicit button press); its status (`quality_rejected` /
  `ready_for_visual_analysis` / `analyzing` / `completed` / `failed`) is
  derived from already-persisted fields, not a guess. `/chat` survives a
  refresh (`GET /api/chat/sessions/{id}/messages` reconstructs the full
  conversation, trace included, from Phase 7's already-persisted rows),
  and a chat can optionally be linked to an existing analysis/product/
  routine/comparison so the agent receives it as trusted context without
  spending a real tool call. Phase 5/6's routine-analysis/comparison
  endpoints stay stateless *by default*, exactly as designed — Phase 8
  adds an opt-in `persist` field rather than reversing that guarantee. A
  real latent bug fixed along the way: `SkinAnalysis.status` could reach
  `analyzing`/`failed` in the Phase 1 schema, but no code ever set
  either — a crash mid-pipeline left a row silently stuck forever; both
  are now wired. One migration (two new tables, four new nullable
  `ChatSession` columns). See [docs/persistence.md](persistence.md).
- **Phase 9** — frontend product polish: zero new backend logic, three
  small additive read-only endpoints (`GET /api/sessions/{id}/products`,
  `.../routine-analyses`, `.../comparisons`, mirroring the Phase 8
  `.../analyses`/`.../chats` pattern exactly — a query + a summary
  schema each, no new columns/migration) so a real **History** page
  (`/history`) could exist at all. Every page now surfaces data an
  endpoint already returned but the UI didn't render yet (visual
  observation `method`, severities, citations, limitations) rather than
  computing anything new. Three duplicated style-map definitions
  (severity badges in `SingleProductAnalyzer`/`ProductComparer`/
  `routine`, agent-status badges in `chat`) collapsed into one
  `StatusBadge`/`SeverityBadge`/`AgentStatusBadge` component set;
  `LimitationList`/`ErrorState`/`EmptyState` replace hand-rolled
  duplicated markup. `/compare` and `/routine` gained an opt-in "save to
  session history" checkbox (using Phase 8's existing `persist` field);
  saved items now show up on `/history` alongside skin analyses and
  chats, each summarized (never recomputed) from already-persisted
  state. `NavBar` gained a working mobile hamburger menu and
  `aria-current` on the active route; a dead placeholder component was
  deleted. Zero backend business logic changed; zero new migrations. See
  [docs/frontend.md](frontend.md).
- **Phase 10** — end-to-end integration + safety hardening, not new
  functionality: a full repository audit against medical/diagnostic
  safety, LLM trust boundaries, prompt injection, tool-call safety,
  numeric/citation safety, disclaimer handling, data/upload safety,
  session safety, and error handling. A deterministic, post-hoc
  diagnostic-claim validator now backstops the system prompt's existing
  "never diagnose" instruction (mirroring how the existing
  `OVERCLAIM_PATTERNS` check already backstops "never guarantee
  safety"), reused by both the Phase 6 explanation layer and the Phase 7
  agent. Unicode normalization (NFKC + zero-width-character stripping)
  hardens every textual safety check against a trivial bypass. A
  decompression-bomb guard closes a real gap in image upload handling
  (a crafted file with an enormous declared decoded size previously hit
  an unhandled 500). A global exception handler gives every unhandled
  error the same sanitized response shape every controlled error
  already used. Everything else audited — the no-auth/access-by-
  possession session model, tool-registry exact-name dispatch,
  citation/numeric grounding, API contract alignment — was confirmed
  already solid by direct code reading and left unchanged; found gaps
  that were explicitly out of scope (no auth, no idempotency
  infrastructure, no image-deletion job) are documented, not built.
  Zero migrations. See [docs/safety.md](safety.md).
- **Phase 11** — a reproducible evaluation harness (`backend/evaluation/`,
  a package separate from and never imported by the application, plus
  `backend/tests/evaluation/` pytest integration): 104 cases across 7
  subsystems (vision, ingredients, routine, comparison, LLM explanation,
  agent, safety), every case calling real production code against its
  actual output rather than a second, parallel implementation of any
  check. Fully offline by default — every LLM/agent case uses
  `FakeLLMProvider`, zero network access or API key required, verified
  with `docker run --network none`. No combined "AI accuracy" number
  anywhere — every metric is reported per subsystem. Run it with
  `pytest tests/evaluation/` (regression gate, no report file) or
  `python -m evaluation` (writes a JSON report to
  `evaluation/reports/`). **Not a clinical accuracy benchmark** — the
  vision fixtures are procedurally generated synthetic images proving
  deterministic pipeline behavior on controlled inputs, never real-world
  or medical accuracy; this is stated explicitly, repeatedly, and
  prominently in [docs/evaluation.md](evaluation.md) rather than
  left implicit. Zero migrations, zero frontend changes.
- **Phase 12** — final testing, documentation, Docker reproducibility,
  security, and portfolio polish. Not new functionality: a repository
  audit (stale language, dead code, broken doc links, endpoint drift,
  overclaiming, terminology) found the codebase already in strong shape
  and fixed the two real issues it turned up (an unused import; a
  README tagline claiming "multimodal LLM reasoning" that contradicted
  the LLM's actual text-only input). Verified via a genuinely clean
  rebuild (`docker compose down -v` + `build --no-cache` + `up`, from an
  empty database) that the full backend suite (752 tests) and evaluation
  harness (104/104) both still pass, and via a full browser smoke test
  across every major flow (image analysis with refresh-without-recompute,
  ingredient analysis + AI explanation, product comparison with history
  persistence, routine analysis, agent chat with a real tool trace, chat
  resumed from History, and controlled handling of an LLM-unavailable
  provider, malformed input, an unknown ingredient, and a corrupted
  image upload). This was the final planned phase — see the README's
  "Future work" section for what's deliberately not built.
