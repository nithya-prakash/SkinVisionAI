# Frontend (Phase 9)

This document covers the Next.js frontend's screen inventory, shared
component set, and the session/history UX Phase 9 added on top of
Phase 8's persistence. See [docs/phase-9-plan.md](phase-9-plan.md) for
the approved plan this was built from (kept for history; this document
is the as-built reference).

## Principle: zero skincare logic in the frontend

The frontend never computes an ingredient compatibility verdict, a
severity, a routine order, or an AI explanation — it only collects
input, calls the backend, and renders exactly what came back. Every
screen below maps to one or more of the endpoints in
[docs/api.md](api.md); none add client-side scoring or recommendation
logic on top.

## Screens

| Route | Purpose | Backed by |
|---|---|---|
| `/` | Landing page: three capability cards (visual analysis, ingredient/routine analysis, AI assistant), disclaimer | Static — no API call |
| `/analyze` | Photo upload, quality gate, kicks off visual analysis | `POST /api/analysis/upload`, redirects to `/results/{id}` |
| `/results/[id]` | Visual analysis results, fetched (never recomputed) on load; explicit re-run button | `GET /api/analysis/{id}`, `POST /api/analysis/{id}/visual-analysis` |
| `/compare` | Two-mode page: single-product ingredient analysis, or two-product comparison | `POST /api/products/analyze`, `POST /api/products/compare`, `POST /api/explanations/{product,compare}` |
| `/routine` | Routine builder: overlapping actives, compatibility notes, suggested AM/PM order | `POST /api/routine/analyze`, `POST /api/explanations/routine` |
| `/chat` | AI assistant with an expandable "How SkinVision AI reached this answer" tool trace; persists and hydrates across refresh | `POST /api/agent/chat`, `GET /api/chat/sessions/{id}/messages` |
| `/history` | Session/history browser — everything this session analyzed, compared, or asked (Phase 9, new) | `GET /api/sessions/{id}/{analyses,chats,products,routine-analyses,comparisons}` |

## Session persistence

`lib/session.ts` wraps `localStorage` (`skinvision_session_id`,
`skinvision_chat_session_id`) so a page refresh doesn't lose continuity.
`getOrCreateAppSession()` is the one call every write-triggering page
(`/analyze`, `/compare`, `/routine`, `/chat`) makes before its first
request; `/history` reads the stored id but deliberately never creates
one — a session with nothing in it is not worth fabricating just to
show an empty page (see `EmptyState`'s "no session yet" branch). See
[docs/persistence.md](persistence.md) for the backend side of this
model.

## The History page (Phase 9, new)

`app/history/page.tsx` is session-scoped: it reads the stored session
id and, if present, fetches all five session-list endpoints in
parallel. Each section renders its own `EmptyState` when that list is
empty rather than hiding the section — a session that has chatted but
never compared two products should still show "No saved product
comparisons yet," not silently omit the section.

Two of the five sections link to a full detail view (skin analyses to
`/results/{id}`; chats resume in `/chat` by writing the chosen chat id
into `localStorage` before navigating). The other three
(products/routine analyses/comparisons) render as summary cards only —
Phase 5/6's product/routine/comparison endpoints are pure functions of
their input, not fetchable-by-id resources (Phase 8 persists a JSON
*snapshot* of the result for the summary, not a re-fetchable detail
endpoint of its own; see [docs/persistence.md](persistence.md)), so
there is nothing further to navigate to without re-running the
analysis, which History deliberately does not do on the user's behalf.

The three session-list endpoints these last sections need
(`GET /api/sessions/{id}/products`, `.../routine-analyses`,
`.../comparisons`) did not exist before Phase 9 — they were added as
small, additive, read-only endpoints mirroring the exact
`list_session_analyses`/`list_session_chats` pattern Phase 8 already
established (a query + a summary schema each; titles/counts derived at
query time from already-stored fields, no new columns, no migration).
See [docs/api.md](api.md#sessions-phase-8-phase-9-adds-productsroutine-analysescomparisons).

`/compare` and `/routine` each gained an opt-in "Save this result to
your session history" checkbox, wired to the `persist` field Phase 8
already added to `POST /api/products/compare` and
`POST /api/routine/analyze`. Unchecked (the default) preserves the
exact byte-identical stateless behavior those endpoints have always
had; checked, the response's `id` becomes a link ("Saved to your
session history. View history.") straight to `/history`.

## Shared components

Built only where ≥2 pages had actual, verified duplication (not
speculative) — see `docs/phase-9-plan.md` §4 for the before/after audit
each one is based on.

| Component | File | Replaces |
|---|---|---|
| `StatusBadge` / `SeverityBadge` / `AgentStatusBadge` | `components/StatusBadge.tsx` | Three independently-drifted severity style maps (`SingleProductAnalyzer` defined and exported one, `ProductComparer` imported it, `routine/page.tsx` redefined its own separate copy instead of importing) plus `chat/page.tsx`'s own agent-status label map |
| `LimitationList` | `components/LimitationList.tsx` | The "Limitations" bordered box, byte-for-byte duplicated across `ResultsClient`, `SingleProductAnalyzer`, `ProductComparer`, `routine/page.tsx` |
| `ErrorState` | `components/ErrorState.tsx` | Hand-rolled `role="alert"` red boxes, each page with slightly different markup |
| `EmptyState` | `components/EmptyState.tsx` | New for Phase 9 — used by `/history`'s "no session yet" / "no items yet" states |
| `Disclaimer` | `components/Disclaimer.tsx` | Gained an optional `text` prop (Phase 9) so `/compare`/`/routine`/`/chat` can pass the exact backend `disclaimer` string instead of always showing `/results/[id]`'s visual-analysis-specific sentence |

`SectionCard`, `LoadingState`, `Citation`, `ToolTrace`, and
`AnalysisCard` were considered and **not** built — each page's actual
layout differs enough (a citation inside `AIExplanation` looks
different from one inside `ProductComparer`'s interaction card) that a
shared shape would fight the content rather than simplify it.

## Accessibility

- `NavBar` (`components/NavBar.tsx`): `aria-current="page"` on the
  active route; a mobile hamburger (`aria-expanded`/`aria-controls`)
  collapsing the link list below `sm:`.
- `/compare`'s mode tabs: `role="tablist"`/`role="tab"` with matching
  `id`/`aria-controls` on each tab and `role="tabpanel"`/
  `aria-labelledby` on each panel.
- Every previously placeholder-only form control (`ProductComparer`'s
  and `routine/page.tsx`'s category/time-of-day `<select>`s, the chat
  message `<input>`) gained an explicit `aria-label`.

## Dead code removed (Phase 9)

`components/PagePlaceholder.tsx` — the Phase 1 scaffold placeholder,
confirmed to have zero remaining imports once every screen had a real
implementation — was deleted rather than left as unreferenced code.
