# Deterministic Ingredient Engine

**Status: Phase 4 implemented.** Parser, normalizer, and compatibility
engine are complete, source-cited, fully tested, and wired to
`POST /api/products/analyze`. Phase 5 ([docs/routine.md](routine.md))
builds routine-level analysis and product comparison on top of this
engine without duplicating any of its logic.

## Why deterministic, not LLM-inferred

Ingredient compatibility is a factual, rule-based question — the kind of
thing an LLM can state confidently and incorrectly. This project computes
it entirely in versioned, tested Python so results are reproducible,
explainable, and never fabricated. The LLM may *call* this engine as a
tool (Phase 7) and *narrate* its output, but never computes a
compatibility verdict, a score, or a citation itself. Nothing in
`app/ingredients/` makes a network or LLM call, anywhere, ever — see
[Determinism and offline guarantee](#determinism-and-offline-guarantee).

## Scope: small and curated, not a database

27 canonical ingredients and 6 compatibility rules — a portfolio-scope
engine demonstrating architecture, not an attempt at a comprehensive
cosmetic-ingredient database. Every rule is sourced from a real,
independently verifiable page at a recognized medical/dermatology
institution (Cleveland Clinic, American Academy of Dermatology) — no rule
was invented, and interactions I could not find a directly-on-topic,
authoritative source for (e.g. a general "combining multiple exfoliating
acids" caution, and a "niacinamide + vitamin C" compatibility claim) were
**deliberately omitted** rather than asserted from indirect/weak evidence.
Absence of a rule always means "not represented in this small rule set,"
never "confirmed safe" — see [Wording policy](#wording-policy).

## Module layout

```
backend/app/ingredients/
├── parser.py         Splits raw ingredient-list text into tokens
├── normalizer.py       Resolves tokens to canonical ingredients via the rule set
├── compatibility.py     Finds pairwise interactions among normalized ingredients
├── rules.py              Loads/validates/indexes the versioned rule files
└── models.py             Internal typed representation of the rule files

backend/rules/ingredients/
├── aliases.json           Canonical ingredients + their known aliases
├── categories.json         Category -> canonical ingredient names
└── compatibility.json       Pairwise interaction rules
```

`app/schemas/ingredient.py` holds the public API contract
(`Ingredient`, `NormalizedIngredient`, `RuleSeverity`,
`IngredientInteraction`, `CompatibilityResult`); `app/ingredients/models.py`
holds the separate, internal typed shape of the on-disk rule files, so the
file format can evolve without touching the API contract.

## Parser (`parser.py`)

Deterministically splits raw INCI-style text (`"Water, Niacinamide,
Glycerin, Panthenol"`) into tokens on commas, semicolons, newlines, and
`/`. The `/` delimiter correctly handles the common INCI convention of
listing one ingredient's synonyms together (`"Water / Aqua / Eau"` — all
three resolve to the same canonical ingredient anyway, so splitting them
has no effect on the final result); it would incorrectly split a compound
ingredient name that itself contains a literal `/` — none of this
project's 27 canonical ingredients have such a name, so that tradeoff is
accepted rather than adding special-case logic for a scenario the rule set
doesn't cover. Empty/whitespace-only input or delimiter-only input parses
to an empty list — a no-op, not an error. Original casing and wording are
always preserved.

## Normalizer (`normalizer.py`)

Resolves each token against the loaded rule set by casefolding and
whitespace-collapsing, then checking, in order: exact canonical name (or
its auto-derived space-separated form — see below), then known alias, then
ambiguous-alias table. An unrecognized token is returned with
`matched: false` — **never guessed at**:

```json
{ "raw_text": "Niacinamide", "normalized_name": "niacinamide", "matched": true, "categories": ["barrier_support", "brightening"] }
{ "raw_text": "SomeMadeUpCompoundXYZ", "normalized_name": null, "matched": false, "categories": [] }
```

An ingredient may carry more than one category (niacinamide is both
`barrier_support` and `brightening`).

### Ambiguous aliases are never silently resolved

Some common terms genuinely refer to more than one distinct ingredient.
Rather than guess, these are listed in `aliases.json`'s
`ambiguous_aliases` map and returned with `ambiguous: true` and every
`candidates`:

```json
{ "raw_text": "Vitamin A", "matched": false, "ambiguous": true, "candidates": ["retinaldehyde", "retinol", "retinyl_palmitate", "tretinoin"] }
{ "raw_text": "Vitamin C", "matched": false, "ambiguous": true, "candidates": ["ascorbic_acid", "magnesium_ascorbyl_phosphate", "sodium_ascorbyl_phosphate"] }
```

## A real bug found while testing: canonical names vs. natural spacing

Canonical names are stored `snake_case` (`glycolic_acid`) as a
Python-identifier-style key. Early testing against the *default shipped
rule set* (not a synthetic fixture) showed that "Glycolic Acid",
"Salicylic Acid", and "Ascorbic Acid" — all real, common INCI names —
failed to normalize at all, because the casefolded input
(`"glycolic acid"`, a space) never matched the stored canonical name
(`"glycolic_acid"`, an underscore). Only single-word canonical names
(retinol, niacinamide, water) happened to work by accident. Fixed in
`rules.py` by registering each multi-word canonical name's
space-separated form as an implicit alias for itself at load time, with a
collision check identical to an explicit alias's. Verified by rerunning
the full test suite, which then passed. This is called out here
deliberately, per this project's policy of reporting real bugs found
during verification rather than only reporting successes.

## Compatibility engine (`compatibility.py`)

```python
check_ingredient_compatibility(ingredient_list: list[str]) -> CompatibilityResult
```

1. Normalizes every token (blank/whitespace-only tokens are silently
   skipped — not malformed input, just a no-op).
2. Deduplicates by **canonical** ingredient (repeated ingredients never
   produce duplicate findings), while `ingredients` in the result still
   lists every original token for traceability.
3. Generates every pair of matched canonical ingredients and looks up a
   rule for each, **checking both orders** — a rule authored as
   `retinol` + `glycolic_acid` matches an input of either order, without
   the rule file needing to duplicate itself.
4. Returns unmatched tokens separately in `unknown_ingredients`, never as
   an error.

```python
check_pair(ingredient_a: str, ingredient_b: str) -> IngredientInteraction
```

A second entry point that always returns exactly one result for a single
specific pair — including an explicit `no_known_conflict` finding when
nothing matches. Not used by the current API (bulk analysis only omits
unmatched pairs from `interactions` rather than listing every
`no_known_conflict` combination, to avoid combinatorial noise), but built
for a natural future agent tool: *"can I use X with Y?"* (Phase 7).

No LLM call, no network call, no randomness anywhere in either function —
see [Determinism and offline guarantee](#determinism-and-offline-guarantee).

## Rule schema and severity model

Each rule in `compatibility.json`:

```json
{
  "rule_id": "retinol_glycolic_acid_caution",
  "ingredient_a": "retinol",
  "ingredient_b": "glycolic_acid",
  "severity": "caution",
  "message": "Combining retinol with glycolic acid may increase irritation. Many dermatology sources suggest alternating nights...",
  "reason": "Both retinol and glycolic acid (an AHA) can irritate skin on their own; layering them increases that risk for many users.",
  "source": "Cleveland Clinic",
  "source_url": "https://my.clevelandclinic.org/health/treatments/23293-retinol",
  "last_verified": "2026-09-08"
}
```

`rule_id`, `ingredient_a`, `ingredient_b`, `severity`, `message`, `reason`,
`source`, and `source_url` are all **required** — `rules.py` rejects a
rule missing any of them at load time (see
[Load-time validation](#load-time-validation-fails-loudly-never-silently)).
Optional: `conditions`, `notes`.

Four severities, and the engine never collapses them into one bucket:

| Severity | Meaning | Stored in a rule file? |
|---|---|---|
| `incompatibility` | Meaningfully reduces efficacy or is broadly discouraged | Yes, if defensibly supported (none currently authored — see scope) |
| `caution` | May increase irritation for some users; not a reason to avoid | Yes — 3 of the 6 current rules |
| `informational` | Worth knowing (often a *complementary* pairing), not a warning | Yes — 3 of the 6 current rules |
| `no_known_conflict` | Explicitly checked; nothing in this rule set matches | **Never** — produced dynamically only, by `check_pair`; rejected by schema validation if authored in a file |

## The current 6 rules

| Rule | Ingredients | Severity | Source |
|---|---|---|---|
| `retinol_glycolic_acid_caution` | retinol + glycolic acid | caution | Cleveland Clinic |
| `retinol_salicylic_acid_caution` | retinol + salicylic acid | caution | Cleveland Clinic |
| `retinol_benzoyl_peroxide_caution` | retinol + benzoyl peroxide | caution | American Academy of Dermatology |
| `retinol_ascorbic_acid_informational` | retinol + vitamin C | informational | Cleveland Clinic |
| `retinol_niacinamide_informational` | retinol + niacinamide | informational | Cleveland Clinic |
| `retinol_hyaluronic_acid_informational` | retinol + hyaluronic acid | informational | Cleveland Clinic |

Note the two `informational` rules for niacinamide and hyaluronic acid are
**positive/complementary** findings (both are commonly cited as helping
offset retinol-related irritation) — this project does not treat every
interaction as a warning, per its wording policy.

## Source policy

Sources were verified by fetching the actual pages (not assumed from
memory or a blog aggregation) before being cited:

- [Cleveland Clinic — Retinol](https://my.clevelandclinic.org/health/treatments/23293-retinol) — directly covers combining retinol with glycolic acid, salicylic acid, vitamin C, niacinamide, and hyaluronic acid.
- [American Academy of Dermatology — Acne treatment](https://www.aad.org/public/diseases/acne/derm-treat/treat) — covers retinoid + benzoyl peroxide combination medications and their documented side effects.

Two candidate rules were investigated and **intentionally not added**:

- **Niacinamide + vitamin C "compatible"** — widely repeated online, but
  the only relevant authoritative page found (Cleveland Clinic's
  hyperpigmentation page) lists both as separate treatment options
  without directly addressing combining them. Rather than stretch that
  into an affirmative "safe to combine" rule, no rule was added; the
  engine's honest default (`no_known_conflict`, not "safe") already
  covers this pair correctly.
- **Multiple exfoliating acids together (general AHA+BHA caution)** — no
  clean, directly-on-topic authoritative source was found (only general
  "don't over-exfoliate" guidance, not a specific pairwise claim). Omitted
  for the same reason.

**Adding a new rule always requires a real, fetched, checkable source at
authoring time** — never one recalled from general knowledge. See
[How to add a new rule](#how-to-add-a-new-rule).

## Load-time validation fails loudly, never silently

`rules.py` validates the three rule files as a coherent whole, every time
the process starts (and in every test that loads a rule set) — no
malformed or inconsistent rule data can enter the system quietly. It
raises `RuleLoadError` for:

- malformed JSON, or a file that doesn't match its Pydantic schema (e.g.
  missing `source`/`source_url`, a non-`http(s)` `source_url`, or an
  unsupported `severity` value — including `no_known_conflict`, which is
  refused if anyone tries to author it directly)
- a duplicate `canonical_name` in `aliases.json`
- an alias that collides with a different canonical name, or with another
  alias pointing elsewhere
- an `ambiguous_aliases` entry with fewer than two candidates, or
  referencing an unknown canonical ingredient
- `categories.json` referencing an unknown canonical ingredient
- a duplicate `rule_id`, a rule referencing an unknown canonical
  ingredient, a rule with `ingredient_a == ingredient_b`, or two rules
  authored for the same pair (rules are symmetric — only one is needed)

## Determinism and offline guarantee

`app/ingredients/` performs no network I/O and calls no LLM anywhere.
Every rule file is read once from local disk and cached in memory
(`get_rule_set()`, a process-wide `lru_cache` singleton); every
parsing/normalization/compatibility function is a pure computation over
that in-memory data. This is verified directly, not assumed: the entire
`tests/ingredients/` suite (91 tests) passes when run inside a Docker
container started with `--network none` (no network interface at all) —
see the Phase 4 completion report for the actual command and result. No
`LLM_API_KEY` or any other secret is read anywhere in this code path.

## Wording policy

- An unknown ingredient is never described as "safe" — only "no supported
  rule is available."
- A pair with no matching rule is never described as "definitely safe
  together" — only "no known conflict is represented in the current rule
  set," with an accompanying limitation explaining that absence of a rule
  is not proof of safety.
- `caution` findings are worded as elevated-risk-for-some-users, never as
  "dangerous" or "unsafe," unless a rule's own source explicitly supports
  that stronger language (none currently do).
- Every `CompatibilityResult` always carries a limitations entry stating
  that real-world tolerability depends on concentration, formulation, pH,
  frequency, application timing, individual sensitivity, skin barrier
  condition, and the rest of the routine — this is a simplified
  educational model, not a clinical assessment.
- This system never produces an overall "skin health score" or a
  universal "better/worse" verdict for a product — `CompatibilityResult`
  has no such field, and its schema (`extra="forbid"`) prevents one from
  being silently added later.

## API

`POST /api/products/analyze` — see [docs/api.md](api.md) for the full
request/response shape. Persists the product, its normalized ingredients,
and the full compatibility result (`Product.analysis_result`, a JSON
column added in this phase's only migration) so it need not be
recomputed on every future read.

## Frontend

`/compare`'s "Analyze One Product" tab collects a product name, optional
category, and raw ingredient text, and renders the backend's
`CompatibilityResult` verbatim — normalized ingredients with categories,
interactions with severity badges and source links, unrecognized
ingredients, and limitations. **No ingredient logic exists in
TypeScript** — the frontend only displays what the backend already
computed and validated. Two-product comparison (`/compare`'s other tab)
and routine analysis (`/routine`) are Phase 5 — see
[docs/routine.md](routine.md).

## How to add a new rule

1. **Verify the interaction** against a real, authoritative source —
   fetch the actual page (don't rely on recalled/summarized knowledge).
   Prefer dermatology organizations, academic/medical institutions, or
   established dermatology patient-education sources over blogs or brand
   marketing pages.
2. **Choose the right severity** — `incompatibility` only if the source
   clearly and defensibly supports that strength of claim;
   `caution` for a documented irritation/tolerability concern;
   `informational` for a sequencing tip or a complementary/positive
   pairing that isn't a warning at all. When in doubt, prefer the weaker
   severity.
3. **Add canonical ingredient/category references first** — if either
   ingredient isn't already in `aliases.json`, add it there (with any
   real aliases) and to `categories.json` before referencing it in a rule;
   `rules.py` will refuse to load a rule that references an unknown
   ingredient.
4. **Add the rule** to `backend/rules/ingredients/compatibility.json`
   with a unique `rule_id`, both ingredient names, `severity`, `message`,
   `reason`, `source`, `source_url`, and today's date as `last_verified`.
5. **Run the app** (or just `python -c "from app.ingredients.rules import get_rule_set; get_rule_set()"`)
   — a malformed or inconsistent rule fails immediately and loudly.
6. **Add tests** — at minimum a known-pair compatibility test
   (`tests/ingredients/test_compatibility.py`) exercising both ingredient
   orders.
7. **Run the complete test suite** and fix any failures before
   considering the rule done.

Never add a rule you couldn't defend by pointing at the fetched source
page.
