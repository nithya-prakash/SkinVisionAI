# Evaluation Harness (Phase 11)

**Status: implemented.** This document describes the evaluation harness
as built. See [docs/history/phase-10-plan.md](history/phase-10-plan.md)-style history:
the plan this replaced lived in this same file (Phase 1 placeholder,
kept accurate rather than a separate archived plan doc, since the
original placeholder never diverged from what got built).

## Purpose

Measures whether the system behaves correctly and safely, as a
reproducible engineering tool -- not a collection of manually inspected
examples, and not a claim of clinical accuracy. See
[Not a clinical accuracy benchmark](#not-a-clinical-accuracy-benchmark)
below; read that section before trusting any number in this document.

It answers questions like: does the CV pipeline behave deterministically?
Does the ingredient engine return the rules it's supposed to? Does the
agent select the right tool and stay grounded? Does the system resist
prompt injection? Does it behave safely when the LLM is unavailable? Do
future changes introduce regressions in any of the above?

## Architecture

The harness preserves the same separation of concerns as the application
itself: deterministic subsystems are evaluated against exact expected
outputs; LLM/agent subsystems are evaluated against *structural safety
and grounding properties* (validation status, forbidden substrings),
never against LLM-generated text treated as if it were correct. The
harness never becomes a second source of truth -- every runner calls the
real production function (`app.vision.analyzer.run_visual_analysis`,
`app.ingredients.compatibility.check_pair`, `app.agent.agent.run_agent`,
etc.) and checks its actual output; nothing in `app/` was changed to
make evaluation easier.

```
backend/
├── evaluation/                  the harness itself -- separate package, never imported by app/
│   ├── __main__.py               `python -m evaluation` entry point
│   ├── report.py                 JSON report assembly/writing
│   ├── metrics.py                 pass_rate, field_level_accuracy, assert_deterministic, overall_counts
│   ├── datasets/                  one module per subsystem -- the actual fixtures + expected results
│   │   ├── vision.py
│   │   ├── ingredients.py
│   │   ├── routine.py
│   │   ├── comparison.py
│   │   ├── llm.py
│   │   ├── agent.py
│   │   └── safety.py
│   ├── runners/                   one module per subsystem -- runs its dataset against real production code
│   │   ├── base.py                 EvalResult, SubsystemSummary, malformed-case guards
│   │   ├── vision_runner.py
│   │   ├── ingredients_runner.py
│   │   ├── routine_runner.py
│   │   ├── comparison_runner.py
│   │   ├── llm_runner.py
│   │   ├── agent_runner.py
│   │   └── safety_runner.py
│   └── reports/                    generated JSON reports (gitignored; `.gitkeep` only)
└── tests/evaluation/               pytest integration: runs every dataset as real tests + tests the harness itself
```

**Adaptations from a from-scratch layout**, made deliberately rather
than by default:

- No separate `expected/` or `fixtures/` directory -- each case's
  expected result is a field on the case itself (e.g.
  `CompatibilityCase.expect_rule_id`), co-located with its input so the
  two can never drift apart in separate files.
- `backend/datasets/` (an existing Phase 1 scaffold directory,
  `images/questionnaires/routines/products/expected_outputs`, all
  empty) is **not** reused for these fixtures -- its `images/` subtree
  is specifically gitignored for real/binary photo content, which this
  harness never has (every image is procedurally generated at runtime;
  see below), and its other subdirectories don't match what Phase 11
  actually needed (`vision/ingredients/routine/comparison/agent/safety`).
  Reusing it would have meant either fighting its existing shape or
  leaving it empty and duplicating structure elsewhere anyway.

## Running it

Two complementary ways to run the suite, matching this project's
existing Docker-based test workflow:

```bash
# As part of the regular test suite -- CI/regression gate, no report
# file written, exits non-zero on any failure like any other test run.
docker compose exec api pytest tests/evaluation/

# Standalone, with a full JSON report written to evaluation/reports/ --
# use this when you want the machine-readable report itself, not just
# pass/fail.
docker compose exec api python -m evaluation
```

Both are **fully offline by default**: every case uses `FakeLLMProvider`
or a pure deterministic engine call. No `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, or network connection is required or used anywhere in
the default suite. Verified explicitly with
`docker run --network none ... python -m evaluation`-style checks (see
the Phase 11 completion report for the exact command run).

No optional live-provider evaluation exists in this phase -- the brief's
"isolate and make it explicitly optional" instruction only applies if
one is added; none was, since every case's ground truth here is either a
deterministic engine or the structural grounding contract a fake
provider already exercises completely.

## Datasets

Every dataset is small, transparent, and version-controlled Python (not
a binary blob or an opaque JSON export) -- every expected result is
reviewable in a code diff.

### Vision (`evaluation/datasets/vision.py`)

Procedurally generated synthetic images (reusing
`tests.helpers.images`'s exact generators -- no second image-generation
implementation), each built to produce one clear, controlled signal:
acceptable/dark/overexposed/low-resolution/low-contrast for the quality
gate; uniform/textured/red-tinted/neutral-gray/highlight/color-gradient/
spotted for the five visual-observation features. Every observation
expectation is expressed as "at least/at most this heuristic level"
(never a pinned exact score), matching the existing unit test suite's
own convention -- calibrated against the real pipeline's actual output,
not assumed. 15 cases, including one 3x-repeat determinism check.

### Ingredients (`evaluation/datasets/ingredients.py`)

Ground truth is the production rule files
(`rules/ingredients/{aliases,categories,compatibility}.json`), loaded
through the real `get_rule_set()` -- no new rules added. Covers
canonical names, aliases, capitalization, whitespace, multi-word
ingredients, both documented ambiguous aliases ("vitamin a", "vitamin
c" -- confirmed never guessed), unknown ingredients, blank-token
dropping, duplicate-token preservation, and **all 6 currently shipped
compatibility rules** (retinol paired with glycolic acid, salicylic
acid, benzoyl peroxide, ascorbic acid, niacinamide, hyaluronic acid),
each also checked in reverse argument order. 28 cases.

### Routine (`evaluation/datasets/routine.py`)

Ground truth is `rules/routine/{overlap,ordering}.json`. Covers
duplicate-active overlap detection (including the specific
retinoid/AHA/vitamin-C pairs the brief named), AM and PM step ordering,
the one documented sunscreen-defaults-to-AM exception, a sunscreen
explicitly requested for PM correctly left unscheduled (no fabricated
position), an unknown category, and unspecified time-of-day. 10 cases.

### Comparison (`evaluation/datasets/comparison.py`)

Shared/only-in-A/only-in-B ingredient sets, a cross-product compatibility
interaction, unknown ingredients kept attributed to the correct side,
and duplicate ingredients within one product's own list. One dedicated
structural case (`comparison_never_produces_a_better_product_score`)
asserts `ProductComparisonResult`'s actual Pydantic field set contains
no score/winner/rating/recommend/rank-shaped field -- checked against
the schema itself, not example output. 8 cases.

### LLM explanation layer (`evaluation/datasets/llm.py`)

Drives the real Phase 6 pipeline
(`app.services.explanation_service.explain_product` ->
`app.llm.validation.validate_explanation`) via a scripted
`FakeLLMProvider` -- never a second validator. Covers a valid grounded
explanation, an unsupported ingredient claim, an unsupported citation
(lead-in phrase and bare URL), an unsupported numeric claim, a
diagnostic claim (Phase 10's validator), an overclaiming safety phrase,
an empty-but-honest explanation, and a simulated provider timeout. Every
case also confirms the deterministic analysis is never withheld,
regardless of whether the explanation itself was accepted. 9 cases.

### Agent (`evaluation/datasets/agent.py`)

Drives the real Phase 7 loop (`app.agent.agent.run_agent`) with the real
`ToolRegistry`. Covers tool selection for all 5 tools, "no tool
necessary" cases (a greeting, an out-of-scope question), grounding
(accepted vs. rejected), unknown-tool and malformed/missing-argument
requests (rejected safely, loop continues), `AGENT_MAX_TOOL_CALLS` and
`AGENT_MAX_TURNS` enforcement under sustained pressure, bounded
tool-result size (`app.agent.trace.bound_tool_result`, tested directly),
and a 3x-repeat determinism check. 19 cases. **What "tool selection"
does and doesn't prove** is documented directly in the dataset module's
own docstring -- most cases hand-script which tool the (simulated) model
requests, proving the dispatch/execution/grounding pipeline works for
each tool, not that a real LLM's judgment was correct; two cases use
`FakeLLMProvider`'s unscripted default heuristic instead, which does
make a real (if simple) content-based choice.

### Safety (`evaluation/datasets/safety.py`)

A dedicated attack dataset covering every category the brief named:
prompt injection, system-prompt extraction, API-key extraction, hidden-
reasoning extraction, arbitrary-code-execution requests, unsupported
diagnosis, unsupported skincare claims, fabricated citation, fabricated
URL, fabricated numeric result, a Unicode zero-width-character bypass
attempt, a case-variation bypass attempt, a malformed tool call, an
unknown tool call, and malicious text embedded in an ingredient/product
field. Each case is explicit about what it proves: most script a
*misbehaving* simulated model (the structural validator backstop, which
doesn't rely on the system prompt having worked) rather than only a
well-behaved one, since that's the more rigorous test. Every case
inspects the actual structured `AgentLoopResult` -- status, the literal
answer text for forbidden substrings, that the system prompt never
appears verbatim, that a rejected turn's answer is empty, and that no
failed tool-trace entry has a fabricated non-`None` result. 15 cases.

## Metrics (`evaluation/metrics.py`)

- **`pass_rate`** -- fraction of cases passed; used for safety pass
  rate, tool-selection accuracy, grounding pass rate, and general
  exact-match accuracy alike (what "passed" means is decided by each
  runner's own comparison logic, not by this function).
- **`field_level_accuracy`** -- fraction of named fields matching
  between an actual and expected dict, for structured results where
  only some fields matter for a given check.
- **`assert_deterministic`** -- calls a function N times (default 3)
  and confirms every call returns an identical result; used by every
  deterministic subsystem's dedicated determinism case.
- **`overall_counts`** -- sums total/passed/failed across subsystem
  summaries for the report's top-level `overall` block.

**No combined "AI accuracy" number exists anywhere in this harness.**
Every metric is reported per subsystem. A 100% ingredient-parsing pass
rate and an 80% agent-grounding pass rate mean very different things;
averaging them would hide exactly the failure a reader most needs to
see. `python -m evaluation`'s printed summary and JSON report both keep
every subsystem's numbers separate, plus one plain aggregate
(`overall.passed`/`overall.failed`/`overall.pass_rate`) that is an
engineering count, never a claim about anything beyond "how many of
these checks passed."

## Report format

`python -m evaluation` writes `evaluation/reports/eval-<run_id>.json`
(and overwrites `evaluation/reports/latest.json`):

```json
{
  "run_id": "a4bf8e2db06f",
  "timestamp": "2026-09-09T07:36:25.853753+00:00",
  "offline": true,
  "overall": { "total": 104, "passed": 104, "failed": 0, "pass_rate": 1.0 },
  "subsystems": {
    "vision": { "total": 15, "passed": 15, "failed": 0, "pass_rate": 1.0, "failures": [] },
    "ingredients": { "...": "..." },
    "routine": { "...": "..." },
    "comparison": { "...": "..." },
    "llm": { "...": "..." },
    "agent": { "...": "..." },
    "safety": { "...": "..." }
  },
  "not_a_clinical_benchmark": "..."
}
```

Each subsystem block includes `total`/`passed`/`failed`/`pass_rate` and
a `failures` list (`case_id`, `description`, `message`) for anything
that didn't pass -- enough to locate and reproduce a failure without
re-running anything. The report never includes an API key, the system
prompt, hidden reasoning, a filesystem secret, or raw sensitive data --
every `EvalResult.actual`/`expected` value is a small, explicitly
constructed primitive (a status string, a level, a sorted list of
ingredient names), never a raw object or an unfiltered LLM response
dump; `tests/evaluation/test_harness_internals.py` verifies the report
stays JSON-safe and free of exactly these strings.

## Regression detection

Every case that isn't purely deterministic still produces the same
result every time it's run, because `FakeLLMProvider`'s scripted
responses are Python objects fixed in the dataset, not sampled from
anything — so a red test in `pytest tests/evaluation/` (or a
`failures` entry in a `python -m evaluation` report) means a real
behavior change happened in the code between runs, not sampling noise.
Wire `pytest tests/evaluation/` (or the whole suite, which includes it)
into CI the same way the rest of this project's tests already are.

## Maintaining and extending the evaluation dataset

A practical guide for adding or changing a case, written for whoever
picks this project up next.

**Where the cases live.** All 104 cases are plain Python data in
`backend/evaluation/datasets/` — one module per subsystem
(`vision.py`, `ingredients.py`, `routine.py`, `comparison.py`, `llm.py`,
`agent.py`, `safety.py`). There is no separate fixtures directory, no
JSON/YAML case format, and no generator script — a case is a dataclass
instance in the same file as every other case for that subsystem, with
its expected result as a field on the case itself (see
[Architecture](#architecture) above for why). `backend/evaluation/runners/`
has the matching runner per subsystem, and `backend/tests/evaluation/`
wires each dataset into pytest.

**How to add a new case:**

1. Open the dataset module for the subsystem you're touching (e.g.
   `evaluation/datasets/agent.py` for a new agent tool — see
   [docs/agent.md](agent.md#adding-a-new-agent-tool-developer-runbook)
   step 9 for the agent-specific version of this).
2. Add a new case instance to that module's tuple of cases, following
   the existing dataclass shape exactly (e.g. `CompatibilityCase`,
   `ToolSelectionCase`). Give it a unique, descriptive `case_id`
   (existing ones read like
   `"agent_tool_selection_compatibility_question"` — specific enough to
   locate the exact scenario from a failure report alone) and a
   one-line `description` of what it proves.
3. Compute the expected result by actually running the real production
   code against your input first (e.g. call `get_rule_set()` or
   `check_ingredient_compatibility(...)` directly in a Python shell, or
   run the case through `pytest tests/evaluation/` once with an
   intentionally wrong `expect_*` value and read the failure's actual
   value from the assertion message) — never hand-guess an expected
   value and never copy one from documentation. The dataset must always
   describe what the code actually does, not what a doc or comment
   claims it does.
4. Run `docker compose exec api pytest tests/evaluation/ -k <your_case_id>`
   (or the whole suite) to confirm it passes, then run the full suite
   once more to confirm nothing else broke.

**When it's correct to change an expected result** — the deterministic
rule or logic it's checking genuinely changed on purpose (a rule file
in `backend/rules/` was intentionally edited, a scoring threshold in
`app/vision/` was deliberately retuned, a schema field was added). In
that case, update the expectation *and* explain why in the commit —
the dataset should always describe current, intended behavior.

**When changing an expected result is actually hiding a regression** —
if a case starts failing and the fix under consideration is "update the
expected value to match the new (failing) output" without first
understanding *why* the output changed, stop. Check whether a code
change caused an unintended behavior shift (a rule file edit that
affected a pair it wasn't meant to, a refactor that altered rounding,
an agent change that broke grounding for an existing tool) before
touching the expectation. A dataset that gets silently "fixed" to match
whatever the code currently does stops being a regression gate and
becomes a tautology — the whole point of [Regression
detection](#regression-detection) above is that a red case means
something real changed.

**Running the harness:**

```bash
docker compose exec api pytest tests/evaluation/     # regression gate, no report file
docker compose exec api python -m evaluation            # standalone run + JSON report
```

Both run fully offline by default (see [Running it](#running-it) above)
— no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` or network access is used, so
there's nothing extra to configure to run either command locally or in
Docker.

**Reviewing cases when a deterministic rule changes.** Any edit to
`backend/rules/ingredients/*.json` or `backend/rules/routine/*.json`
should be followed by re-running `tests/evaluation/` before merging,
specifically checking:

- Did any *existing* case's expectation start failing (an unintended
  side effect of the rule change)?
- Does the change need a *new* case (a new compatibility rule, a new
  canonical ingredient, a new routine-ordering exception) so the change
  itself is covered going forward, not just the rules that already
  existed?

**Why these numbers are not a clinical/medical accuracy claim.** Every
number this harness reports is an engineering correctness and
regression-protection metric, never a diagnostic or clinical accuracy
measurement — see [Not a clinical accuracy benchmark](#not-a-clinical-accuracy-benchmark)
below for the full reasoning. Practically, this means: never add a case
whose framing implies real-world medical ground truth (e.g. "correctly
detects rosacea"), and never cite a pass rate as if it were a
sensitivity/specificity figure in a report, resume, or conversation
about this project.

## Not a clinical accuracy benchmark

**This is the single most important thing to understand about this
harness.** It does not measure, and this project does not claim:

- clinical accuracy
- dermatological diagnostic accuracy
- medical sensitivity/specificity
- real-world skin-condition detection accuracy

The vision fixtures are procedurally generated synthetic images with
deliberately controlled properties (a flat color, isolated
high-frequency noise, a red tint) -- they demonstrate that the pipeline
responds correctly and *deterministically* to a known, controlled input.
They say nothing about accuracy against real skin, real lighting
conditions, real cameras, or any medical condition, and no dataset here
would change that even if it were much larger, because none of it is
real, clinically-sourced, or clinically-labeled data. If a genuinely
sourced and appropriately licensed clinical dataset and methodology are
ever added to this project, that would be a distinct, explicitly-scoped
future decision -- not an extension of this harness's existing fixtures.

This harness measures: engineering correctness (does the deterministic
code do what it's supposed to on a known input), regression protection
(does a code change break a previously-passing behavior), and safety
compliance (is an attack or a validator-violating claim actually
blocked, checked structurally). That is the whole, honest scope.

## Known limitations

- Vision fixture expectations were calibrated against this pipeline's
  actual current output (documented directly in code comments where a
  first-guess expectation didn't match reality and was corrected) --
  they are internally consistent and reviewable, not derived from an
  external ground truth.
- "Tool selection accuracy" for 3 of the 5 agent tools is measured via
  hand-scripted requests (proving dispatch/execution/grounding), not a
  real LLM's judgment -- see the Agent dataset section above.
- No live-provider (real Anthropic/OpenAI) evaluation path exists. If
  useful in a future phase, it should be added as an explicitly
  separate, clearly-optional path, never folded into the default
  offline suite.
- Safety cases are a curated, representative set of attack categories,
  not an exhaustive adversarial-ML red-team corpus.
