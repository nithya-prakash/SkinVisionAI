# Routine Analysis & Product Comparison

**Status: Phase 5 implemented.** Overlap detection, cross-product
compatibility, AM/PM ordering, and product-vs-product comparison are
complete, deterministic, stateless, and fully tested.

## Why this builds on Phase 4 instead of duplicating it

Ingredient compatibility is Phase 4's job, already deterministic, tested,
and source-cited. Phase 5 adds **routine-level** reasoning on top —
multiple products at once, duplicate actives, and a suggested application
order — without re-implementing any ingredient logic. Every routine
analysis and every product comparison calls straight into
`app.ingredients.{parser,normalizer,compatibility}` (see
[docs/ingredients.md](ingredients.md)); nothing in `app/routine/` or
`app/products/comparator.py` encodes an ingredient interaction rule.

## Architecture

```
Products -> ingredient parsing -> normalization -> category detection
   (all Phase 4, reused verbatim)
         |
         +--> cross-product compatibility analysis (Phase 4's engine,
         |     run once over the whole routine's ingredients)
         |
         +--> overlap detection (app/routine/overlap.py)
         |
         +--> routine ordering rules (app/routine/ordering.py)
         |
         v
   Structured RoutineAnalysisResult
```

## Module layout

```
backend/app/routine/
├── analyzer.py    Orchestrates the above into one RoutineAnalysisResult
├── overlap.py       Duplicate/overlapping active-ingredient detection
├── ordering.py       Deterministic AM/PM step placement
├── rules.py            Loads/validates/indexes the routine rule files
└── models.py            Internal typed representation of those files

backend/app/products/
└── comparator.py    Deterministic two-product comparison

backend/rules/routine/
├── ordering.json    AM/PM step-order table + one sourced ordering rationale
└── overlap.json       "Active" ingredient categories + one sourced overlap rationale
```

Two rule files, not three: the master architecture offered
`ordering.json` / `overlap.json` / `routine_rules.json` as one option.
The sourced "ordering guidance" and "overlap guidance" assertions were
folded directly into `ordering.json` and `overlap.json` respectively
(each already needed a `source`/`source_url`/`reason` for its own
methodology) rather than kept in a third file — there was no remaining
content that would have justified a separate `routine_rules.json`, and
splitting further would have been organization for its own sake.

## Cross-product compatibility: how it avoids duplicating Phase 4

`app.routine.analyzer.analyze_routine` collects every product's raw
ingredient tokens, concatenates them into **one list for the whole
routine**, and calls `app.ingredients.compatibility.check_ingredient_compatibility`
on it exactly once. Phase 4's engine already deduplicates by canonical
ingredient and checks every pair — so this single call finds every
interaction anywhere in the routine, whether both ingredients came from
the same product or different ones, with zero routine-specific rule
logic. `app.products.comparator.compare_products` does the same thing
over exactly two products' combined tokens.

The only routine-specific work is **provenance**: mapping each finding's
two ingredients back to which product(s) contained them, so the API
response can say "found via Retinol Serum + Acid Toner" rather than just
"retinol + glycolic_acid."

**Deduplication across products, not just within one:** if the same
active (e.g. glycolic acid) appears in two different products that both
also contain retinol, the `retinol_glycolic_acid_caution` rule fires
**once**, listing every product that contributed either ingredient — not
once per product pair. Verified directly:
`tests/routine/test_analyzer.py::test_same_interaction_via_multiple_products_is_deduplicated`.

## Overlap detection

`app.routine.overlap.find_overlapping_actives` flags a canonical
ingredient when it (a) appears in **two or more distinct products** and
(b) belongs to a category the versioned rule set considers an "active"
worth flagging (`retinoid`, `aha`, `bha`, `vitamin_c`, `acne_treatment` —
see `rules/routine/overlap.json`). Ordinary base ingredients (water,
glycerin, preservatives) are excluded by design — flagging every shared
humectant would be noise, not signal, and the master brief's own example
concerns an active (retinol), not a base ingredient.

Wording is fixed, sourced, and never escalated by this code:

> "Repeated exposure to the same active may increase irritation potential
> depending on formulation, concentration, and frequency."

— American Academy of Dermatology, [*"A dermatologist's guide to
skincare"*](https://www.aad.org/news/dermatologist-guide-skincare)
(fetched and verified directly, not recalled).

## AM/PM ordering: suggestion, not requirement

`app.routine.ordering.suggest_ordering` places each product at a
deterministic step position using `rules/routine/ordering.json`'s
category → step-order table, sourced from AAD's [*"Should I apply my
skin care products in a certain order?"*](https://www.aad.org/public/everyday-care/skin-care-basics/care/apply-skin-care-certain-order):
cleanser → treatment/serum/exfoliant → moisturizer → sunscreen (AM only).
That source lists moisturizer and sunscreen at the same stage; this
model places sunscreen last within that stage (a reasonable extension
this model makes, not something the source states verbatim) — see the
`reason` field in `ordering.json` for the exact, disclosed wording.

**Never a requirement.** Every result is worded as a *suggestion*:
`RoutineAnalysisResult.limitations` always includes *"Suggested routine
order is a general educational guideline, not a required or medically
correct order — actual product layering can depend on formulation and
manufacturer instructions"* whenever any ordering was suggested at all.

### Unknown category or unspecified time: never fabricated

- **Unknown category** (`category` omitted) → the product is never
  placed anywhere; it appears in `unscheduled_products` with an explicit
  reason. A category the ordering table doesn't recognize (`other`, or
  any category without a rule for the requested time of day) behaves
  identically — no position is invented.
- **Unspecified time of day** → no schedule is invented either, with
  **exactly one** documented, deterministic exception: a product whose
  `category` is explicitly `sunscreen` is placed in the AM sequence even
  with `time_of_day: unspecified`, because "sunscreen" is a definitional,
  self-declared product category (not an inferred ingredient property) —
  matching the master brief's explicit instruction that sunscreen
  placement may rely only on an explicit category, never an inferred one.
  See `app.routine.ordering`'s module docstring.
- **`AM_AND_PM` for a category with no rule in one of the two tracks**
  (e.g. sunscreen has no PM entry) → the product is placed wherever a
  rule exists and simply omitted from the track that has none; it is
  *not* pushed into `unscheduled_products`, since it *was* successfully
  scheduled, just not for both times.

## Product comparison

`POST /api/products/compare` reuses Phase 4 exactly as routine analysis
does — see [above](#cross-product-compatibility-how-it-avoids-duplicating-phase-4).
Additionally computes:

- **Shared / only-in-A / only-in-B** — canonical ingredient names, set
  operations over each product's matched ingredients.
- **Shared active categories** — categories present among *either*
  product's ingredients that are also present among the *other's* (not
  necessarily the same specific ingredient — e.g. two different
  retinoids still share the `retinoid` category).

**No overall score.** `ProductComparisonResult` has no "better product,"
"winner," or numeric rating field, and its schema (`extra="forbid"`)
prevents one from being silently added later — verified by
`tests/products/test_comparator.py::test_no_overall_score_field_exists`.

## Statelessness: why Phase 5 needed no database migration

Both `POST /api/routine/analyze` and `POST /api/products/compare` are
**pure functions of their request body** — deterministic, fast (no
external I/O beyond reading the already-cached in-memory rule set), and
cheap enough to simply re-run rather than cache. Unlike Phase 2/3's image
analysis (expensive to recompute, worth persisting) or Phase 4's
single-product analysis (tied to a specific `Product` record a user might
revisit), a routine analysis or comparison is defined entirely by its
input — there is no "the same one" to fetch later. Persisting either
would add schema and a stale-cache-invalidation problem for no real
benefit, so neither endpoint writes to the database *by default*.
Confirmed by `alembic check` reporting *"No new upgrade operations
detected"* after this phase's entire implementation.

**Update (Phase 8):** a caller who *does* want a retrievable id later
(e.g. to link a chat session to this specific result) can opt in with
`persist: true` — the response then also carries a real `id`. This is
additive, not a reversal: the default (`persist` omitted or `false`)
remains the exact byte-for-byte stateless behavior described above, so
every existing caller of either endpoint is unaffected. See
[docs/persistence.md](persistence.md).

## Unknown ingredients / unsupported combinations

Same policy as Phase 4, applied at the routine level too: an ingredient
the normalizer doesn't recognize is `matched: false`, never assumed safe;
a pair with no rule is never asserted "safe together," only "no known
conflict is represented in the current rule set." No routine-level code
path invents a stronger or weaker claim than what Phase 4's engine
already determined.

## Sources

- [AAD — *Should I apply my skin care products in a certain order?*](https://www.aad.org/public/everyday-care/skin-care-basics/care/apply-skin-care-certain-order) — the ordering methodology.
- [AAD — *A dermatologist's guide to skincare*](https://www.aad.org/news/dermatologist-guide-skincare) — the duplicate-active/overlap caution wording.

Both fetched and verified directly during this phase, not recalled from
general knowledge — the same policy documented in
[docs/ingredients.md](ingredients.md).

## How to add a new routine rule

1. **Ordering change** (e.g. adding a new product category, or
   re-sequencing a step): find a real, on-topic source discussing that
   specific placement, update `rules/routine/ordering.json`'s `am_steps`/
   `pm_steps` and its `reason`/`source`/`source_url`/`last_verified`.
   Adding a category to the table also requires that category to already
   exist in `app.schemas.common.ProductCategory`.
2. **Overlap change** (e.g. adding a new "active" ingredient category to
   flag): confirm the category exists in
   `app.schemas.ingredient.IngredientCategory`, add it to
   `rules/routine/overlap.json`'s `active_categories`, and re-verify the
   `message`/`reason`/`source` still accurately describe the (now wider)
   set of flagged categories.
3. **Never add a routine-specific compatibility rule.** An ingredient
   interaction belongs in Phase 4's `rules/ingredients/compatibility.json`
   (see [docs/ingredients.md](ingredients.md#how-to-add-a-new-rule)) —
   routine analysis and product comparison must keep consuming that one
   source of truth, never a second copy.
4. Run the app (or `python -c "from app.routine.rules import get_routine_rule_set; get_routine_rule_set()"`)
   to confirm the file still loads — a malformed or inconsistent rule
   fails immediately and loudly.
5. Add tests in `tests/routine/` or `tests/products/` and run the
   complete suite before considering the change done.

## Limitations

- The ordering table covers 8 `ProductCategory` values with a single,
  general-purpose sequence; it does not represent every dermatologist's
  or manufacturer's specific product-line instructions.
- Sunscreen's "always last in AM" placement extends its cited source's
  actual wording (which only groups moisturizer and sunscreen together)
  with this model's own reasonable inference — disclosed above and in
  `ordering.json`'s `reason` field, not presented as a direct quote.
- Overlap detection only flags 5 ingredient categories as "actives"; a
  product-formulation-level judgment about what counts as a meaningfully
  irritating repeat exposure is inherently more nuanced than a fixed
  category list.
- Cross-product compatibility is exactly as complete as Phase 4's 6-rule
  set — no broader, no narrower.
