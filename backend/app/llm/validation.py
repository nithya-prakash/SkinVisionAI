"""Anti-hallucination validation for LLM explanation output.

A "lightweight validation layer" (per design intent) run on every LLM
response *after* it has already passed Pydantic schema validation, before
it is ever merged into an API response. Three kinds of checks:

1. **Structural** -- every ``rule_id`` / ``ingredient`` the LLM references
   must actually exist in the deterministic result it was given. This is
   exact and deterministic (a simple set-membership check).
2. **Textual** -- the LLM's free-text fields (summary, key points,
   per-item explanations, routine notes) are scanned for a fixed set of
   patterns that would indicate overclaiming, a fabricated numeric claim,
   a fabricated citation, a mention of an ingredient that was never part
   of this analysis, or a diagnostic/medical claim (Phase 10 -- see
   ``DIAGNOSTIC_CLAIM_PATTERN`` below). This is necessarily heuristic
   (natural-language text can't be perfectly verified by pattern
   matching) -- see docs/llm.md's limitations section. It is
   deliberately biased toward over-rejecting rather than
   under-rejecting, appropriate for a safety validator.
3. **Unicode normalization** (Phase 10) -- every text check above runs
   against NFKC-normalized, zero-width-character-stripped text, so a
   trivial bypass attempt (e.g. a zero-width space inserted mid-word)
   can't dodge a substring/regex match that would otherwise catch it.
   See ``normalize_for_validation`` below and docs/safety.md.

Nothing here calls an LLM, the network, or performs any randomness --
fully deterministic and independently testable.
"""
from __future__ import annotations

import re
import unicodedata

from app.ingredients.rules import get_rule_set
from app.llm.context import DeterministicContext
from app.llm.schemas import ExplanationLLMOutput

# Phrases that assert or strongly imply guaranteed safety -- the
# deterministic engine never makes this claim (see docs/ingredients.md's
# wording policy), so the explanation layer must not either.
OVERCLAIM_PATTERNS: tuple[str, ...] = (
    "completely safe",
    "totally safe",
    "100% safe",
    "fully safe",
    "guaranteed safe",
    "definitely safe",
    "perfectly safe",
    "entirely safe",
    "always safe",
    "no risk at all",
    "risk-free",
    "risk free",
    "safe to use together",
    "safe for everyone",
)

# A bare percentage or "X out of Y" / "X/Y" score -- the deterministic
# engine's own 0-1 scores are never phrased this way in its output, so
# this pattern in LLM prose is a fabricated-feeling calculation.
NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d{1,3}\s?%|\b\d+(?:\.\d+)?\s*(?:out of|/)\s*\d+\b", re.IGNORECASE)

URL_PATTERN = re.compile(r"https?://\S+")
CITATION_LEAD_IN_PATTERN = re.compile(
    r"\baccording to\b|\bsource:\s|\bcited by\b|\bstudy (?:by|from|published)\b|\bper the\b",
    re.IGNORECASE,
)

# --- Diagnostic-claim detection (Phase 10) ---------------------------------
#
# Everything above catches the LLM inventing a *fact*. This catches it
# crossing the app's other hard line: never diagnosing a medical
# condition, even though the system prompt already instructs it not to
# (app/llm/prompts.py rule 11, app/agent/prompts.py rule 8/9). Prompting
# alone is not a structural guarantee -- this is the deterministic,
# post-hoc backstop, mirroring how OVERCLAIM_PATTERNS backstops the
# "never guarantees safety" prompt instruction.
#
# Conservative by design: it only fires on an *assertion directed at the
# user* ("you have acne", "this is rosacea"), never on a condition name
# used educationally ("a routine for acne-prone skin", "won't cure
# eczema, but may help") or on a deferral to a professional ("if you
# have persistent acne, see a dermatologist"; "you don't have rosacea").
# Both of the latter are excluded by construction, not by a separate
# negation check: the pattern requires the assertion verb to sit
# *immediately* next to both "you"/"this" and the condition name (only a
# short, fixed set of articles allowed between them), so a negation word
# ("don't", "not", "isn't") or a qualifier ("persistent", "diagnosed
# with") breaks the required adjacency and the pattern simply doesn't
# match. See tests/llm/test_validation.py for the full positive/negative
# case matrix this is checked against.
DIAGNOSTIC_CONDITIONS: tuple[str, ...] = (
    "acne",
    "rosacea",
    "eczema",
    "dermatitis",
    "psoriasis",
    "melanoma",
    "skin cancer",
    "skin disease",
    "confirmed skin disease",
    "medical condition",
)
_DIAGNOSTIC_LEAD_INS = ("a case of ", "signs of ", "an ", "a ", "")
_DIAGNOSTIC_ASSERTION_VERBS = (
    "have",
    "has",
    "had",
    "suffer from",
    "suffers from",
    "show signs of",
    "shows signs of",
    "appear to have",
    "appears to have",
)


def _alternation(options: tuple[str, ...]) -> str:
    return "|".join(re.escape(opt) for opt in options)


_DIAGNOSTIC_COND_ALT = _alternation(DIAGNOSTIC_CONDITIONS)
_DIAGNOSTIC_LEAD_IN_ALT = _alternation(_DIAGNOSTIC_LEAD_INS)
_DIAGNOSTIC_VERB_ALT = _alternation(_DIAGNOSTIC_ASSERTION_VERBS)

DIAGNOSTIC_CLAIM_PATTERN = re.compile(
    r"\byou(?:'re| are) experiencing (?:" + _DIAGNOSTIC_LEAD_IN_ALT + r")(?:" + _DIAGNOSTIC_COND_ALT + r")\b"
    r"|\byou (?:" + _DIAGNOSTIC_VERB_ALT + r") (?:" + _DIAGNOSTIC_LEAD_IN_ALT + r")(?:" + _DIAGNOSTIC_COND_ALT + r")\b"
    r"|\bthis (?:is|looks like|appears to be|sounds like) (?:"
    + _DIAGNOSTIC_LEAD_IN_ALT
    + r")(?:"
    + _DIAGNOSTIC_COND_ALT
    + r")\b"
    r"|(?<!not )(?<!n't )(?<!never )\brequires? medical treatment\b"
    r"|\bdiagnos(?:is|e|ed|ing) (?:based on|from) (?:the |this )?(?:image|photo|picture)\b",
    re.IGNORECASE,
)

# --- Unicode normalization (Phase 10) --------------------------------------
#
# Scoped, narrow defense-in-depth: NFKC-fold compatibility characters
# (e.g. full-width digits) and strip the handful of zero-width
# characters that could otherwise be inserted mid-word to dodge a plain
# substring/regex match (e.g. "100​%" would not match
# NUMERIC_CLAIM_PATTERN unnormalized). Deliberately *not* a general
# homoglyph/confusable-character detector -- that is a much larger,
# harder-to-maintain problem this phase does not attempt to solve.
_ZERO_WIDTH_CHARS = (
    "\u200b",  # zero width space
    "\u200c",  # zero width non-joiner
    "\u200d",  # zero width joiner
    "\ufeff",  # zero width no-break space / BOM
    "\u2060",  # word joiner
)


def normalize_for_validation(text: str) -> str:
    """NFKC-normalize ``text`` and strip zero-width characters. Every
    check in this module runs on the result, never on the raw LLM text.
    """
    normalized = unicodedata.normalize("NFKC", text)
    for char in _ZERO_WIDTH_CHARS:
        normalized = normalized.replace(char, "")
    return normalized


class HallucinationError(Exception):
    """Raised when LLM output fails anti-hallucination validation.

    ``code`` is a stable, machine-readable reason (used in tests and
    logs); ``message`` is human-readable detail. Never includes the raw
    LLM output verbatim in a way that would be shown to end users -- see
    ``app.services.explanation_service`` for how this is surfaced.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def all_llm_output_text(output: ExplanationLLMOutput) -> str:
    parts = [output.summary, *output.key_points, *output.routine_notes]
    parts.extend(item.explanation for item in output.interactions_explained)
    parts.extend(item.explanation for item in output.overlap_explained)
    return " ".join(parts)


def mentioned_known_ingredients(text: str) -> set[str]:
    """Return every canonical ingredient name from the *entire* ingredient
    rule set that appears (by its natural-spaced name or a known alias)
    as a substring of ``text``, case-insensitively. Normalizes ``text``
    first (see ``normalize_for_validation``) so this stays correct even
    when called directly, not only via ``validate_explanation`` below.
    """
    rule_set = get_rule_set()
    lowered = normalize_for_validation(text).lower()
    mentioned: set[str] = set()

    for canonical in rule_set.canonical_names:
        spaced = canonical.replace("_", " ")
        if spaced in lowered:
            mentioned.add(canonical)

    for alias, canonical in rule_set.alias_index.items():
        if alias in lowered:
            mentioned.add(canonical)

    return mentioned


def validate_explanation(output: ExplanationLLMOutput, context: DeterministicContext) -> None:
    """Raise ``HallucinationError`` if ``output`` references or asserts
    anything not present in ``context``. Returns normally if the output
    is safe to merge into the final API response.
    """
    for item in output.interactions_explained:
        if item.rule_id not in context.known_rule_ids:
            raise HallucinationError(
                "unknown_interaction",
                f"references rule_id {item.rule_id!r}, which is not present in the "
                "deterministic result",
            )

    for item in output.overlap_explained:
        if item.ingredient not in context.known_overlap_ingredients:
            raise HallucinationError(
                "unknown_overlap_ingredient",
                f"references ingredient {item.ingredient!r} as an overlapping active, "
                "which is not present in the deterministic result",
            )

    combined_text = normalize_for_validation(all_llm_output_text(output))
    lowered = combined_text.lower()

    for phrase in OVERCLAIM_PATTERNS:
        if phrase in lowered:
            raise HallucinationError(
                "overclaim", f"contains an overclaiming safety phrase: {phrase!r}"
            )

    diagnostic_match = DIAGNOSTIC_CLAIM_PATTERN.search(combined_text)
    if diagnostic_match:
        raise HallucinationError(
            "diagnostic_claim",
            "contains language that asserts or implies a medical diagnosis: "
            f"{diagnostic_match.group(0)!r}",
        )

    if NUMERIC_CLAIM_PATTERN.search(combined_text):
        raise HallucinationError(
            "fabricated_number",
            "contains a numeric/percentage claim not present in the deterministic result",
        )

    for url in URL_PATTERN.findall(combined_text):
        if url.rstrip(".,)") not in context.known_source_urls:
            raise HallucinationError(
                "fabricated_citation", f"references a URL not present in the deterministic result: {url}"
            )

    if CITATION_LEAD_IN_PATTERN.search(combined_text):
        if context.known_source_names and not any(
            name.lower() in lowered for name in context.known_source_names
        ):
            raise HallucinationError(
                "fabricated_citation",
                "references a source/citation not present in the deterministic result",
            )

    mentioned_ingredients = mentioned_known_ingredients(combined_text)
    unknown_mentions = mentioned_ingredients - context.known_ingredient_names
    if unknown_mentions:
        raise HallucinationError(
            "unknown_ingredient",
            f"mentions ingredient(s) not present in this analysis: {sorted(unknown_mentions)}",
        )
