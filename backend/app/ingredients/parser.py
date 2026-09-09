"""Deterministic parsing of raw INCI-style ingredient list text.

Splits on common delimiters, trims whitespace, and preserves each token's
original text -- it never invents, corrects, drops, or reorders
ingredients beyond removing empty tokens. No LLM or network call is used
anywhere in this module.

Known simplification: "/" is treated as a delimiter, which correctly
splits the common INCI convention of listing a single ingredient's
synonyms together (e.g. "Water / Aqua / Eau" -- all resolve to the same
canonical ingredient via aliases.json, so splitting them has no effect on
the final result). It would incorrectly split a compound ingredient name
that itself contains a literal "/" (e.g. some copolymer INCI names) --
none of this project's small, curated canonical ingredient list has such
a name, so this tradeoff is accepted rather than adding special-case
logic for a scenario the rule set doesn't cover.
"""
from __future__ import annotations

import re

_DELIMITERS = re.compile(r"[,;\n/]+")
_WHITESPACE = re.compile(r"\s+")


def parse_ingredient_list(raw_text: str | None) -> list[str]:
    """Split a raw ingredient-list string into individual ingredient tokens.

    Returns an empty list for empty/whitespace-only/delimiter-only input
    -- that is a no-op, not an error. Each returned token retains its
    original casing and internal wording; only surrounding whitespace and
    a single trailing period are trimmed.
    """
    if not raw_text:
        return []

    tokens: list[str] = []
    for chunk in _DELIMITERS.split(raw_text):
        cleaned = _WHITESPACE.sub(" ", chunk).strip()
        cleaned = cleaned.rstrip(".").strip()
        if cleaned:
            tokens.append(cleaned)
    return tokens
