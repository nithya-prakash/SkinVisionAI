"""Ingredient evaluation fixtures (Phase 11).

Ground truth here is the *production rule files*
(``backend/rules/ingredients/{aliases,categories,compatibility}.json``),
loaded through the real ``app.ingredients.rules.get_rule_set()`` --
never a second, hand-maintained copy of what the engine should return.
No new rules are added for evaluation purposes; every case below
exercises a fact already present in those files.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizationCase:
    """One raw ingredient token, run through the parser + normalizer."""

    case_id: str
    description: str
    raw_text: str
    expect_matched: bool
    expect_canonical: str | None = None
    expect_ambiguous: bool = False
    expect_candidates: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ParseListCase:
    """A full raw ingredient-list string, testing parser-level behavior
    (blank tokens, duplicates) rather than a single token's resolution.
    """

    case_id: str
    description: str
    raw_text: str
    expect_tokens: tuple[str, ...]


@dataclass(frozen=True)
class CompatibilityCase:
    """Two ingredients, checked against the real compatibility rule set."""

    case_id: str
    description: str
    ingredient_a: str
    ingredient_b: str
    expect_rule_id: str | None  # None means "no rule for this pair"
    expect_severity: str | None = None


NORMALIZATION_CASES: tuple[NormalizationCase, ...] = (
    # Canonical, exact spelling.
    NormalizationCase(
        "norm_canonical_retinol", "A canonical ingredient name normalizes to itself",
        raw_text="retinol", expect_matched=True, expect_canonical="retinol",
    ),
    NormalizationCase(
        "norm_canonical_niacinamide", "A canonical ingredient name normalizes to itself",
        raw_text="niacinamide", expect_matched=True, expect_canonical="niacinamide",
    ),
    # Known alias.
    NormalizationCase(
        "norm_alias_aqua_to_water", "The alias 'aqua' resolves to canonical 'water'",
        raw_text="aqua", expect_matched=True, expect_canonical="water",
    ),
    NormalizationCase(
        "norm_alias_bha_to_salicylic_acid", "The alias 'BHA' resolves to canonical 'salicylic_acid'",
        raw_text="BHA", expect_matched=True, expect_canonical="salicylic_acid",
    ),
    # Capitalization variation.
    NormalizationCase(
        "norm_capitalization_uppercase", "Fully uppercase input still resolves correctly",
        raw_text="RETINOL", expect_matched=True, expect_canonical="retinol",
    ),
    NormalizationCase(
        "norm_capitalization_titlecase", "Title-case input still resolves correctly",
        raw_text="Niacinamide", expect_matched=True, expect_canonical="niacinamide",
    ),
    # Whitespace variation.
    NormalizationCase(
        "norm_whitespace_padding", "Leading/trailing whitespace is trimmed before matching",
        raw_text="   retinol   ", expect_matched=True, expect_canonical="retinol",
    ),
    NormalizationCase(
        "norm_whitespace_internal_collapsed", "Extra internal whitespace collapses before matching",
        raw_text="hyaluronic    acid", expect_matched=True, expect_canonical="hyaluronic_acid",
    ),
    # Multi-word ingredient / alias.
    NormalizationCase(
        "norm_multiword_alias_vitamin_b3", "The multi-word alias 'vitamin b3' resolves to niacinamide",
        raw_text="vitamin b3", expect_matched=True, expect_canonical="niacinamide",
    ),
    NormalizationCase(
        "norm_multiword_canonical_hyaluronic_acid", "The two-word canonical name resolves to itself",
        raw_text="hyaluronic acid", expect_matched=True, expect_canonical="hyaluronic_acid",
    ),
    # Ambiguous aliases (must NOT guess a single canonical name).
    NormalizationCase(
        "norm_ambiguous_vitamin_a", "'vitamin a' is a known but ambiguous alias -- never guessed",
        raw_text="vitamin a", expect_matched=False, expect_ambiguous=True,
        expect_candidates=frozenset({"retinol", "retinaldehyde", "retinyl_palmitate", "tretinoin"}),
    ),
    NormalizationCase(
        "norm_ambiguous_vitamin_c", "'vitamin c' is a known but ambiguous alias -- never guessed",
        raw_text="vitamin c", expect_matched=False, expect_ambiguous=True,
        expect_candidates=frozenset(
            {"ascorbic_acid", "sodium_ascorbyl_phosphate", "magnesium_ascorbyl_phosphate"}
        ),
    ),
    # Unknown ingredients (must remain unknown, never silently guessed).
    NormalizationCase(
        "norm_unknown_ingredient", "A token with no match in the rule set stays unmatched",
        raw_text="unobtainium", expect_matched=False, expect_ambiguous=False,
    ),
    NormalizationCase(
        "norm_unknown_misspelling", "A near-miss spelling is not fuzzy-matched -- stays unknown",
        raw_text="retinnol", expect_matched=False, expect_ambiguous=False,
    ),
)


PARSE_LIST_CASES: tuple[ParseListCase, ...] = (
    ParseListCase(
        "parse_blank_tokens_dropped", "Empty tokens from consecutive/trailing delimiters are dropped, not surfaced as unknown",
        raw_text="Water,, Retinol,,, Glycerin,",
        expect_tokens=("Water", "Retinol", "Glycerin"),
    ),
    ParseListCase(
        "parse_duplicate_tokens_preserved", "A duplicated ingredient appears as two separate tokens, not silently deduplicated at parse time",
        raw_text="Retinol, Retinol, Niacinamide",
        expect_tokens=("Retinol", "Retinol", "Niacinamide"),
    ),
    ParseListCase(
        "parse_whitespace_only_is_empty", "Whitespace-only input parses to zero tokens, not an error",
        raw_text="   ",
        expect_tokens=(),
    ),
    ParseListCase(
        "parse_mixed_delimiters", "Commas, semicolons, and slashes all act as delimiters",
        raw_text="Water; Retinol/Glycerin",
        expect_tokens=("Water", "Retinol", "Glycerin"),
    ),
)


# All 6 real, currently-shipped compatibility rules (rule_id/severity read
# directly from rules/ingredients/compatibility.json) plus reverse-order
# variants and a confirmed-absent pair.
COMPATIBILITY_CASES: tuple[CompatibilityCase, ...] = (
    CompatibilityCase(
        "compat_retinol_glycolic_acid", "Documented caution: retinol + glycolic acid",
        "retinol", "glycolic_acid", expect_rule_id="retinol_glycolic_acid_caution", expect_severity="caution",
    ),
    CompatibilityCase(
        "compat_retinol_glycolic_acid_reversed", "Reverse argument order finds the same rule",
        "glycolic_acid", "retinol", expect_rule_id="retinol_glycolic_acid_caution", expect_severity="caution",
    ),
    CompatibilityCase(
        "compat_retinol_salicylic_acid", "Documented caution: retinol + salicylic acid",
        "retinol", "salicylic_acid", expect_rule_id="retinol_salicylic_acid_caution", expect_severity="caution",
    ),
    CompatibilityCase(
        "compat_retinol_salicylic_acid_reversed", "Reverse argument order finds the same rule",
        "salicylic_acid", "retinol", expect_rule_id="retinol_salicylic_acid_caution", expect_severity="caution",
    ),
    CompatibilityCase(
        "compat_retinol_benzoyl_peroxide", "Documented caution: retinol + benzoyl peroxide",
        "retinol", "benzoyl_peroxide", expect_rule_id="retinol_benzoyl_peroxide_caution", expect_severity="caution",
    ),
    CompatibilityCase(
        "compat_retinol_ascorbic_acid", "Documented informational note: retinol + ascorbic acid",
        "retinol", "ascorbic_acid", expect_rule_id="retinol_ascorbic_acid_informational", expect_severity="informational",
    ),
    CompatibilityCase(
        "compat_retinol_niacinamide", "Documented informational note: retinol + niacinamide",
        "retinol", "niacinamide", expect_rule_id="retinol_niacinamide_informational", expect_severity="informational",
    ),
    CompatibilityCase(
        "compat_retinol_hyaluronic_acid", "Documented informational note: retinol + hyaluronic acid",
        "retinol", "hyaluronic_acid", expect_rule_id="retinol_hyaluronic_acid_informational", expect_severity="informational",
    ),
    CompatibilityCase(
        "compat_no_known_conflict", "Two unrelated, real ingredients with no documented rule between them",
        "niacinamide", "hyaluronic_acid", expect_rule_id=None,
    ),
)
