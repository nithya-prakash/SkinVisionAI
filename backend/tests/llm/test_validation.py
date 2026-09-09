"""Tests for app.llm.validation -- the anti-hallucination validator.

Table-driven where practical. Deterministic, offline: constructs
``ExplanationLLMOutput``/``DeterministicContext`` directly, no provider
or network involved.
"""
from __future__ import annotations

import pytest

from app.llm.context import DeterministicContext
from app.llm.schemas import ExplanationLLMOutput, InteractionExplanationItem, OverlapExplanationItem
from app.llm.validation import (
    DIAGNOSTIC_CLAIM_PATTERN,
    HallucinationError,
    normalize_for_validation,
    validate_explanation,
)

CONTEXT = DeterministicContext(
    payload={},
    known_rule_ids=frozenset({"retinol_glycolic_acid_caution"}),
    known_ingredient_names=frozenset({"retinol", "glycolic_acid", "niacinamide"}),
    known_overlap_ingredients=frozenset({"retinol"}),
    known_source_names=frozenset({"Cleveland Clinic"}),
    known_source_urls=frozenset({"https://my.clevelandclinic.org/health/treatments/23293-retinol"}),
)


def _valid_output(**overrides) -> ExplanationLLMOutput:
    data = {
        "summary": "This routine contains retinol and glycolic acid, which have a documented caution.",
        "key_points": ["One caution interaction was found."],
        "interactions_explained": [
            InteractionExplanationItem(
                rule_id="retinol_glycolic_acid_caution",
                explanation="Retinol and glycolic acid may increase irritation when combined.",
            )
        ],
        "overlap_explained": [
            OverlapExplanationItem(ingredient="retinol", explanation="Retinol appears in multiple products.")
        ],
        "routine_notes": [],
    }
    data.update(overrides)
    return ExplanationLLMOutput(**data)


def test_valid_output_passes() -> None:
    validate_explanation(_valid_output(), CONTEXT)  # must not raise


def test_empty_output_passes() -> None:
    validate_explanation(ExplanationLLMOutput(summary="No interactions were found."), CONTEXT)


# --- Critical hallucination tests (master spec section 22) ---


def test_invented_interaction_rejected() -> None:
    """2. Invent a compatibility interaction. Expected: REJECT."""
    bad = _valid_output(
        interactions_explained=[
            InteractionExplanationItem(
                rule_id="totally_fabricated_rule_id_xyz",
                explanation="This is a fake interaction.",
            )
        ]
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "unknown_interaction"


def test_invented_overlap_ingredient_rejected() -> None:
    """1 (structured form). Invent an ingredient reference. Expected: REJECT."""
    bad = _valid_output(
        overlap_explained=[
            OverlapExplanationItem(ingredient="unobtainium", explanation="Fake ingredient overlap.")
        ]
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "unknown_overlap_ingredient"


@pytest.mark.parametrize(
    "phrase",
    [
        "This combination is completely safe.",
        "These two products are totally safe together.",
        "This routine is 100% safe.",
        "Using these together is guaranteed safe.",
        "This pairing is risk-free.",
    ],
)
def test_overclaiming_safety_language_rejected(phrase: str) -> None:
    """3 & 6. Change 'caution' to 'safe' / claim 'completely safe'. Expected: REJECT."""
    bad = _valid_output(summary=phrase)
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "overclaim"


def test_fabricated_citation_url_rejected() -> None:
    """4. Add a fabricated citation. Expected: REJECT."""
    bad = _valid_output(
        key_points=["See https://totally-fake-dermatology-journal.example/study for details."]
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "fabricated_citation"


def test_fabricated_citation_lead_in_rejected() -> None:
    """4 (prose form). Expected: REJECT."""
    bad = _valid_output(summary="According to the Mayo Clinic, this combination is well-studied.")
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "fabricated_citation"


def test_real_source_name_is_not_flagged_as_fabricated() -> None:
    ok = _valid_output(summary="According to Cleveland Clinic, this pairing may increase irritation.")
    validate_explanation(ok, CONTEXT)  # must not raise


@pytest.mark.parametrize(
    "phrase",
    [
        "This routine scores 85% for safety.",
        "There is a 30% chance of irritation.",
        "This gives a compatibility rating of 7 out of 10.",
        "The risk level is 3/10.",
    ],
)
def test_numerical_calculation_rejected(phrase: str) -> None:
    """5. Add a numerical calculation. Expected: REJECT."""
    bad = _valid_output(summary=phrase)
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "fabricated_number"


def test_mentioning_ingredient_not_in_input_rejected() -> None:
    """7. Mention an ingredient not present in the deterministic input.
    Expected: REJECT.
    """
    bad = _valid_output(summary="You might also consider adding salicylic acid to this routine.")
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "unknown_ingredient"


def test_mentioning_ingredient_present_in_input_is_allowed() -> None:
    ok = _valid_output(summary="This routine contains retinol and niacinamide.")
    validate_explanation(ok, CONTEXT)  # must not raise


def test_validation_is_deterministic() -> None:
    output = _valid_output()
    validate_explanation(output, CONTEXT)
    validate_explanation(output, CONTEXT)  # calling twice must behave identically (no raise either time)


# --- Diagnostic-claim detection (Phase 10) ---------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "You have acne.",
        "you have rosacea and should be careful",
        "This is eczema.",
        "This looks like dermatitis.",
        "you have a confirmed skin disease",
        "You have a medical condition.",
        "This requires medical treatment.",
        "We have a diagnosis based on the image.",
        "A diagnosis based on this photo suggests treatment is needed.",
        "YOU HAVE ACNE",  # case variation
        "you're experiencing rosacea",  # case variation / contraction
        "You HAVE Eczema",  # mixed case
    ],
)
def test_obvious_diagnostic_claims_rejected(phrase: str) -> None:
    bad = _valid_output(summary=phrase)
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"


def test_diagnostic_claim_embedded_in_otherwise_valid_answer_rejected() -> None:
    bad = _valid_output(
        summary=(
            "Retinol and glycolic acid have a documented caution-level interaction. "
            "Also, you have acne based on this photo."
        )
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"


def test_diagnostic_claim_in_key_points_rejected() -> None:
    bad = _valid_output(key_points=["This is a confirmed skin disease."])
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"


def test_diagnostic_claim_in_interaction_explanation_rejected() -> None:
    bad = _valid_output(
        interactions_explained=[
            InteractionExplanationItem(
                rule_id="retinol_glycolic_acid_caution",
                explanation="You have acne, so avoid combining these.",
            )
        ]
    )
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"


@pytest.mark.parametrize(
    "phrase",
    [
        # Educational use of a condition name, not an assertion about the user.
        "This routine is often used for acne-prone skin.",
        "Retinol won't cure eczema, but gentle cleansers may help.",
        "Retinol is commonly used in acne treatment products.",
        "This ingredient is well-tolerated across most skin types.",
        # Deferral to a professional -- conditional, not assertive.
        "If you have persistent acne, consult a dermatologist.",
        "If you have been diagnosed with rosacea by a dermatologist, consult them first.",
        # Explicit negation.
        "You don't have rosacea.",
        "This is not acne.",
        "This isn't eczema.",
        "This is not a medical diagnosis.",
        "This does not require medical treatment on its own.",
        # Ordinary educational sentences with no condition language at all.
        "Niacinamide is a well-tolerated ingredient for most skin types.",
        "This routine contains retinol and niacinamide.",
    ],
)
def test_legitimate_educational_wording_not_rejected(phrase: str) -> None:
    ok = _valid_output(summary=phrase)
    validate_explanation(ok, CONTEXT)  # must not raise


def test_diagnostic_claim_error_never_includes_raw_phrase_in_a_way_shown_to_users() -> None:
    """The HallucinationError's message may reference the matched phrase
    for logs/tests, but the caller (explanation_service) never surfaces
    it to the end user -- verified structurally here that the exception
    is raised with a stable, machine-readable code regardless of exactly
    which condition/phrasing triggered it.
    """
    bad = _valid_output(summary="You have psoriasis.")
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"
    assert isinstance(exc_info.value.message, str) and exc_info.value.message


# --- Unicode normalization (Phase 10) --------------------------------------


def test_zero_width_space_inserted_mid_word_does_not_bypass_diagnostic_check() -> None:
    evasive = "you\u200b have\u200b acne"  # zero width space
    assert DIAGNOSTIC_CLAIM_PATTERN.search(evasive) is None  # unnormalized: dodges the pattern
    bad = _valid_output(summary=evasive)
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "diagnostic_claim"


def test_zero_width_joiner_does_not_bypass_overclaim_check() -> None:
    evasive = "this is complete\u200dly safe"  # zero width joiner
    bad = _valid_output(summary=evasive)
    with pytest.raises(HallucinationError) as exc_info:
        validate_explanation(bad, CONTEXT)
    assert exc_info.value.code == "overclaim"


def test_bom_and_word_joiner_stripped() -> None:
    text = "\ufeffyou have\u2060 rosacea"  # BOM + word joiner
    normalized = normalize_for_validation(text)
    assert "﻿" not in normalized
    assert "⁠" not in normalized
    assert DIAGNOSTIC_CLAIM_PATTERN.search(normalized) is not None


@pytest.mark.parametrize(
    "case",
    ["you HAVE acne", "You Have ACNE", "yOu HaVe AcNe"],
)
def test_diagnostic_check_is_case_insensitive(case: str) -> None:
    assert DIAGNOSTIC_CLAIM_PATTERN.search(normalize_for_validation(case)) is not None


def test_fullwidth_digits_normalized_for_numeric_check() -> None:
    # NFKC-folds fullwidth Unicode digits to plain ASCII digits before the
    # numeric-claim regex runs.
    fullwidth = "this has a １００% match"  # "100%" in fullwidth digits
    normalized = normalize_for_validation(fullwidth)
    assert "100%" in normalized


def test_legitimate_multilingual_text_is_unaffected_by_normalization() -> None:
    text = "Ce produit contient de la niacinamide et du glycérol."
    assert normalize_for_validation(text) == text
    ok = _valid_output(summary=text + " This routine contains retinol and niacinamide.")
    validate_explanation(ok, CONTEXT)  # must not raise -- accented text is not itself a bypass attempt


def test_normalization_does_not_break_ingredient_mention_matching() -> None:
    # A legitimate ingredient mention with no evasion characters must
    # still be correctly recognized as present in the deterministic
    # context after normalization -- normalization must not itself
    # introduce a false rejection.
    ok = _valid_output(summary="This routine contains retinol, which is well understood.")
    validate_explanation(ok, CONTEXT)  # must not raise
