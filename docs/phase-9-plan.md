# Phase 9 Plan: Frontend Product Experience

**Status: plan only — nothing in this document has been implemented.**
Per the Phase 9 prompt: inspect, confirm baseline, write this plan, then
STOP. Do not implement anything below until it is explicitly approved.

Grounded in an actual inspection of the repository (every file named
below is real) done immediately before writing this, plus a confirmed
fresh baseline: **596 backend tests passing**, frontend `tsc`/`eslint`
both clean, `next build` clean, all 7 routes generating, against the
currently-running `skinvision-ai-api`/`-web` Docker images.

---

## 1. Current frontend architecture

Next.js App Router (`frontend/src/app`), React 19, TypeScript, Tailwind
v4. 6 routes today: `/`, `/analyze`, `/results/[id]`, `/routine`,
`/compare`, `/chat`. Every page is a client component (`"use client"`)
calling one typed API client (`lib/api.ts`, ~780 lines, zero skincare
logic — confirmed, unchanged invariant since Phase 1) plus `lib/session.ts`
(Phase 8: `localStorage`-backed app/chat session id).

Component inventory (`frontend/src/components/`):

| Component | Used by | Notes |
|---|---|---|
| `NavBar` | root layout, every page | 4 static links, no active-route styling, no mobile menu, no History link |
| `Disclaimer` | every page | **Hardcoded text** including "these observations are visual estimates... camera quality" on every page, including `/compare`, `/routine`, `/chat` where nothing is visual — a real, pre-existing inconsistency (see §2) |
| `AIExplanation` | `SingleProductAnalyzer`, `ProductComparer`, `/routine` | Renders `Explanation` (Phase 6) with a violet "AI-generated" accent, already distinguishes deterministic vs AI content |
| `PagePlaceholder` | **nothing** (dead code) | Was `/chat`'s Phase 1–6 placeholder; orphaned since Phase 7 replaced it with a real chat UI |

Page-level components: `ResultsClient.tsx` (rebuilt Phase 8: fetch-then-render,
explicit status states), `SingleProductAnalyzer.tsx` + `ProductComparer.tsx`
(both live under `/compare`, switched by an in-page tab, not two routes),
`chat/toolSummary.ts` (presentational trace/citation formatting, no
skincare logic).

**No frontend test runner is installed** (`package.json` has no Jest/
Vitest/Playwright/Testing Library — confirmed by reading it directly).
Every prior phase's frontend verification has been `tsc` + `eslint` +
`next build` + live browser verification, never automated component
tests.

## 2. Identified UX problems

Concrete, found by reading the actual current pages (not assumed):

1. **Home (`app/page.tsx`) is minimal Phase-1 scaffolding**: one
   paragraph, one disclaimer box, a single CTA to `/analyze`. It never
   mentions ingredient/routine analysis, product comparison, or the AI
   assistant, and has no links to them — a new visitor cannot discover
   3 of the app's 4 capabilities from the homepage.
2. **`NavBar` has no active-link indicator, no mobile layout, and no
   History link.** At narrow widths, `flex items-center justify-between`
   with the logo + 4 text links has no wrap/overflow handling — worth
   verifying in the browser during implementation, and fixing
   regardless since a hamburger/collapse pattern is needed either way
   once a 5th (History) link is added.
3. **`Disclaimer`'s hardcoded second sentence is visual-analysis-specific
   language shown on every page**, including ones with no visual
   analysis involved (`/compare`, `/routine`, `/chat`). Confusing, not
   incorrect (the sentence is true on `/results/[id]`, meaningless
   elsewhere).
4. **`ResultsClient` never renders `VisualObservation.method`** (e.g.
   `"lab_a_channel_mean"`) even though the field exists and is already
   fetched — Phase 9's brief explicitly asks for "methodology where
   available."
5. **`/routine` visually treats compatibility notes (sourced,
   deterministic facts) and suggested AM/PM ordering (a heuristic
   placement) identically** — both are plain bordered cards with no
   visual distinction between "this is a documented rule" and "this is
   a suggested arrangement," which is exactly the fact-vs-suggestion
   distinction Phase 9 asks for.
6. **No History/session-browsing UI exists at all**, despite Phase 8
   shipping and testing `GET /api/sessions/{id}/analyses` and
   `.../chats`. This is the single largest net-new surface Phase 9
   needs — see §3's Screen 8 section and the decision point in §12.
7. **`PagePlaceholder.tsx` is dead code** (zero imports) — candidate for
   deletion or repurposing as History's empty state; not touched
   without your say-so.
8. **`/compare` combines "Product Analysis" and "Product Comparison"
   into one route with an in-page tab**, not two separate screens as
   Phase 9's screen list (4 and 5) implies. Flagged as a decision point,
   not assumed — see §12.

## 3. Proposed page-by-page improvements

### Screen 1 — Home (`app/page.tsx`)

Rewrite (content only, same route, same minimal-marketing tone the brief
asks for): a short framing paragraph naming the three real components
(computer vision, deterministic rule engine, controlled LLM reasoning —
matching this project's own established language from
`README.md`/`docs/architecture.md`, not new marketing copy), three
capability cards (Visual Analysis → `/analyze`, Ingredient/Routine
Analysis → `/compare` + `/routine`, AI Assistant → `/chat`) each with a
one-line, backend-accurate description and a CTA, the existing
disclaimer, and (if §12's decision is "yes") a link to History. No stock
photography, no gradients — matches the "Design direction" section.

### Screen 2 — Analyze (`app/analyze/page.tsx`)

Already covers upload → quality result → conditional "View Visual
Observations" link, using real backend states (`quality.is_acceptable`,
`quality.issues`). Proposed polish only: clearer visual separation
between the "uploading" and "quality-checked" states (currently both
render inside the same result block once `status==="success"`), and
explicit wording that a rejected-quality image still *has* a
`analysis_id` (already true server-side, so `/results/[id]` for a
rejected image now correctly shows `quality_rejected` per Phase 8 — just
make that reachable/discoverable from `/analyze`'s own rejection state
rather than only from `/results/[id]` after manual navigation).

### Screen 3 — Visual Results (`app/results/[id]/ResultsClient.tsx`)

Already Phase-8-correct (fetch via `GET /api/analysis/{id}`, explicit
`ready_for_visual_analysis`/`analyzing`/`failed`/`completed` states, a
manual "Run/Re-run" button, never auto-recomputes). Additions only:
render `VisualObservation.method` per observation (already fetched,
never shown — item 4 above), and tighten the "quality_rejected" state's
copy to point back to `/analyze` for a retry. No skin score, no dryness
estimation, no condition labels — none exist server-side to render, and
none will be added.

### Screen 4/5 — Product Analysis & Comparison (`app/compare/*`)

Both already render: normalized ingredients with matched/ambiguous/
unmatched states clearly separated (`SingleProductAnalyzer`), severity-
badged compatibility interactions with source links, limitations,
disclaimer, and `AIExplanation`; `ProductComparer` already never computes
a "winner" (confirmed — no score field exists in `ProductComparisonResult`
and none will be added in the frontend). Proposed polish: strengthen the
visual weight of the "unknown ingredients" callout (currently a plain
neutral box, same weight as "limitations") so it reads as its own
category, and a small "Product A" / "Product B" column-header treatment
in the comparison result grid for scannability. See §12 for whether
these stay one route with a tab (recommended) or split into two.

### Screen 6 — Routine (`app/routine/page.tsx`)

Already supports add/remove products, per-product AM/PM/category,
analyze, and renders overlap/compatibility/suggested-AM/suggested-PM/
unscheduled/limitations. Addition: a small label distinguishing
"Compatibility notes" (sourced, deterministic — label as e.g. "Rule")
from "Suggested AM/PM order" (heuristic placement — label as e.g.
"Suggestion"), addressing item 5. No change to any ordering logic itself
(still 100% backend-computed).

### Screen 7 — AI Assistant (`app/chat/page.tsx`)

Already shows the conversation, a status badge for
`tool_error`/`llm_unavailable`/`validation_error`/`max_tool_calls`, the
expandable "How SkinVision AI reached this answer" trace (tool name +
`toolSummary.ts`'s presentational summary + citations), and a "Thinking…"
loading state — and (Phase 8) persists/hydrates history across a
refresh. Proposed polish: distinct icon/color per failure status instead
of one uniform amber badge for all four, and a one-line static caption
near the trace disclosure explaining what it is on first use (e.g. "Every
step below was computed by a deterministic tool, not guessed by the
model") — copy only, no new data.

### Screen 8 — Session/History (new)

The real net-new work this phase. See §12 for the scope decision this
depends on (which sections are buildable against the *current* API
without inventing data, vs. which need a small, justified backend
extension). Proposed regardless of that decision: a new
`app/history/page.tsx`, session-scoped, reading from `lib/session.ts`'s
already-stored session id (redirecting/prompting to create one if none
exists yet — never fabricating one just to show an empty page).

## 4. Proposed shared components

Only where there is actual repetition across ≥2 existing pages (not
speculative):

| Component | Replaces | Justification |
|---|---|---|
| `StatusBadge` | The severity/status badge markup duplicated across 4 files: `SingleProductAnalyzer.tsx` defines `SEVERITY_STYLES`/`SEVERITY_LABELS` and exports them; `ProductComparer.tsx` imports that copy; **`routine/page.tsx` independently redefines its own separate, slightly different `SEVERITY_STYLES` map instead of importing it** (confirmed by reading both files — a real, not hypothetical, duplication); `chat/page.tsx` has its own separate `STATUS_LABELS` for agent statuses | 3 independent style-map definitions + 1 cross-import today, for what is visually the same pill-badge pattern |
| `LimitationList` | The `<div className="rounded-lg border ... Limitations">` block repeated verbatim in `ResultsClient`, `SingleProductAnalyzer`, `ProductComparer`, `routine/page.tsx` | Byte-for-byte duplicated markup in 4 files |
| `EmptyState` / `ErrorState` | The various `role="alert"` red-bordered boxes with a retry button, currently hand-rolled per page | Needed anyway for the new History page's "no session yet" / "no items yet" states |
| `PageHeader` | The `<h1>` + intro `<p>` pattern at the top of every page | Small, but consistent; optional if it doesn't earn its keep once written |

**Not proposed**: `SectionCard`, `LoadingState`, `Citation`, `ToolTrace`,
`AnalysisCard` as separate components — each page's actual layout differs
enough (a citation in `AIExplanation` looks different from one in
`ProductComparer`'s interaction card) that forcing one shared shape now
would fight the content rather than simplify it. Revisit only if real
duplication shows up during implementation.

`Disclaimer` itself: proposed to accept an optional `text` prop
(defaulting to today's full sentence for `/results/[id]`, where it's
accurate) so `/compare`/`/routine`/`/chat` can pass the plain backend
`disclaimer` string instead of the visual-analysis-specific sentence —
fixes item 3 with a one-line, backward-compatible signature change.

## 5. API dependencies

Every page-level change above renders data an existing, tested endpoint
already returns — **no backend change required** for Screens 1–7.
Verified by re-reading the actual response schemas (not assumed):
`VisualObservation.method` (`app.schemas.vision`) already exists and is
already fetched by `ResultsClient` into `analysis.visual_analysis`, just
never rendered; severity/citations/limitations are already present on
every relevant schema.

Screen 8 (History) is the one place API dependencies are a real, open
question — see §12.

## 6. Accessibility plan

- Every form input already has a visible `<label>`/placeholder pattern;
  audit for `<label htmlFor>` vs. placeholder-only fields during
  implementation (`SingleProductAnalyzer`/`ProductComparer`/`routine`'s
  category/time-of-day `<select>`s currently rely on adjacent text, not
  a bound `<label>` — a real gap to fix, found by reading the JSX).
- `NavBar`'s active route: add `aria-current="page"` (currently absent).
- `ComparePage`'s tab buttons (`role="tablist"`/`role="tab"`) are missing
  `aria-controls`/matching `id`s linking each tab to its panel — add
  during the Screen 4/5 pass.
- Focus states: Tailwind's default focus ring is currently relied on
  implicitly (no `focus-visible:` overrides anywhere) — verify contrast
  in both themes rather than assuming it's sufficient.
- Status/error text is already plain readable sentences (no raw error
  objects rendered) — preserved, not weakened.
- New History page: proper heading hierarchy, and empty/loading states
  announced via visible text (not color alone).

## 7. Responsive design plan

Verify (via the browser's `resize_window` tool, actual measurement, not
assumption) at mobile (375px), tablet (768px), and desktop:

- `NavBar` at ≤640px — very likely needs a collapse/hamburger pattern
  once a 5th link is added; confirm current 4-link behavior first before
  deciding the exact pattern.
- `ProductComparer`'s 3-column shared/only-A/only-B grid and the
  comparison result grid — already `grid-cols-1 sm:grid-cols-3`
  (confirmed in the source), verify it doesn't feel cramped once column
  headers are added (§3).
- `/routine`'s per-product card (name + ingredients + category/time-of-day
  selects side by side via `flex gap-3`) — verify it doesn't overflow at
  375px.
- `/chat`'s message bubbles (already `max-w-[85%]`) and the trace
  `<details>` panel — verify readability at mobile width.
- Image upload preview (`/analyze`) — already `max-h-80 w-auto`, verify
  on a narrow viewport.

No layout is expected to need a structural rebuild; this is verification
+ targeted fixes, not a redesign.

## 8. Testing plan

- **Backend**: run the full 596-test suite before and after; zero
  regressions required (no backend code is expected to change for
  Screens 1–7; Screen 8 may add a small, isolated set of new read-only
  endpoints + tests, entirely additive — see §12).
- **Frontend**: `npx tsc --noEmit`, `npm run lint`, `npm run build` after
  every logical group of changes, not only at the end (matching the
  "after each logical group" instruction).
- **No new frontend test framework introduced** — the project has never
  had one, and the "don't introduce heavy tooling unless clearly
  justified" rule plus "optimize for clean architecture, not feature
  count" both argue against adding Jest/Vitest/Testing Library for a
  UI-polish phase. Flagged explicitly as a default, not a silent
  decision — say so if you'd like automated component tests introduced
  instead.
- **Live browser verification** of all 14 items the prompt lists
  (Home, Upload, quality rejection, quality acceptance, visual analysis,
  results refresh, product analysis, product comparison, routine
  analysis, AI explanation, AI agent, chat persistence, session
  persistence, History if implemented) — via the in-app Browser pane,
  same method used for Phases 6–8.

## 9. Security verification plan

Repository-wide grep for API keys/credentials/`NEXT_PUBLIC_`-prefixed
secrets across `frontend/src/` (same sweep already run clean after
Phases 6–8; re-run after Phase 9's changes specifically) — confirm no
new file introduces a credential, and that `lib/session.ts`'s
`localStorage` usage remains limited to plain non-secret UUIDs (already
true, re-verified as part of any History-page work touching that file).

## 10. Files expected to change

`frontend/src/app/page.tsx`, `components/NavBar.tsx`, `components/Disclaimer.tsx`,
`app/analyze/page.tsx`, `app/results/[id]/ResultsClient.tsx`,
`app/compare/SingleProductAnalyzer.tsx`, `app/compare/ProductComparer.tsx`,
`app/compare/page.tsx`, `app/routine/page.tsx`, `app/chat/page.tsx`;
`README.md`, `docs/architecture.md`'s "Frontend" section, `docs/api.md`
only if §12 adds endpoints.

## 11. Files expected to be created

`frontend/src/components/StatusBadge.tsx`, `LimitationList.tsx`,
`EmptyState.tsx`, `ErrorState.tsx`, possibly `PageHeader.tsx` (§4);
`frontend/src/app/history/page.tsx` (+ a small client component if the
page grows large enough to warrant splitting); `docs/frontend.md` (a
dedicated frontend-architecture doc, since the brief asks for a
"frontend documentation section" and the current one is 6 lines inside
`docs/architecture.md` — proposed as a new file linked from there,
matching this project's existing one-doc-per-concern convention rather
than growing `architecture.md` indefinitely).
Backend additions only if §12's extension is approved — see there for
the exact file list.

## 12. Decisions needed from you before implementation starts

1. **History page scope** (the biggest open question). The current API
   supports exactly two of the five sections the brief describes:
   - **Recent skin analyses** — `GET /api/sessions/{id}/analyses` ✅
   - **Chat history** — `GET /api/sessions/{id}/chats` ✅ (though the
     list items carry only `id`/`message_count`/timestamps — no preview
     of what a chat was about, no linked-context indicator)
   - **Recent product analyses / routines / comparisons** — **no
     session-scoped list endpoint exists for any of these.**

   Options:
   - **(a) Ship History with only the two supported sections.** Zero
     backend change. Honest, but visibly incomplete against the brief.
   - **(b) Add three small, additive read-only endpoints** —
     `GET /api/sessions/{id}/products`, `.../routine-analyses`,
     `.../comparisons` — mirroring the exact pattern
     `list_session_analyses`/`list_session_chats` already established in
     `app.services.session_service` (a query + a summary schema each;
     product/routine/comparison "titles" derived at query time from
     already-stored fields — `Product.name`, or the first product name
     in a `RoutineAnalysisRecord.result`/`ComparisonRecord.result` JSON
     blob — no new columns, no new migration). Small, tested, consistent
     with "reuse existing patterns," but is new backend surface in a
     phase framed as frontend-only.
   - **(c) Do (b) but only for product analyses** (the most requested,
     since `/compare`'s "analyze one product" mode is the most-used
     flow), leaving routines/comparisons for a later phase.

   **My recommendation is (b)** — the three endpoints are small,
   mechanical, and directly reuse an already-proven pattern (low risk),
   and a History page that's honestly missing 3 of 5 sections undercuts
   the "coherent unified application" goal this phase exists for. But
   this is your call, not mine to make silently, per the plan's own
   "never invent data" instruction and this project's established
   practice of surfacing exactly this kind of decision rather than
   guessing (see the Phase 8 plan's three decision points).
2. **`/compare`'s combined tab UI vs. two separate routes** (item 8,
   §3's Screen 4/5 note). Recommend **keeping the current combined
   `/compare` route** (already functional, already tested, splitting it
   is pure churn with no functional benefit) — but flagging since the
   brief describes them as two numbered screens.
3. **`Disclaimer` component signature change** (§4) — an optional prop,
   backward compatible, but touches a component used on every page; flag
   in case you'd rather leave the existing (slightly inaccurate on
   non-visual pages) wording alone than risk a subtle regression on
   `/results/[id]` where the current wording is correct.

Everything else in this plan is presentation-only, additive, and
low-risk. If you'd rather I just proceed with the recommended option on
1–3 and start implementing, say so.
