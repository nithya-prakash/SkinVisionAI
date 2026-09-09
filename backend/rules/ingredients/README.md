# Ingredient rules (Phase 4)

Versioned, source-cited rule data backing the deterministic ingredient
engine (`backend/app/ingredients/`). Loaded, schema-validated, and
cross-indexed at process start by `app/ingredients/rules.py`; a malformed
file fails loudly rather than being silently skipped. See
[`docs/ingredients.md`](../../../docs/ingredients.md) for the full
methodology, source policy, and the workflow for adding a new rule.

- **`aliases.json`** — the canonical ingredient list, each with its known
  aliases, plus an `ambiguous_aliases` map for terms (e.g. "Vitamin A")
  that could mean more than one canonical ingredient and are deliberately
  left unresolved rather than guessed.
- **`categories.json`** — functional category → canonical ingredient
  names (an ingredient may appear under more than one category).
- **`compatibility.json`** — pairwise interaction rules (`rule_id`,
  `ingredient_a`, `ingredient_b`, `severity`, `message`, `reason`,
  `source`, `source_url`, `last_verified`). Every rule must cite a real,
  verifiable source — see docs/ingredients.md's source policy. Currently
  6 rules, all sourced from Cleveland Clinic and the American Academy of
  Dermatology, covering retinol's interactions with two exfoliating
  acids, benzoyl peroxide, vitamin C, niacinamide, and hyaluronic acid.

Intentionally a small, curated set — this project does not attempt a
comprehensive cosmetic-ingredient database.
