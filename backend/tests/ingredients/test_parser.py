"""Table-driven tests for app.ingredients.parser."""
from __future__ import annotations

import pytest

from app.ingredients.parser import parse_ingredient_list


@pytest.mark.parametrize(
    "raw_text,expected",
    [
        ("Water, Niacinamide, Glycerin, Panthenol", ["Water", "Niacinamide", "Glycerin", "Panthenol"]),
        ("Water,Niacinamide,Glycerin", ["Water", "Niacinamide", "Glycerin"]),
        ("Water,   Niacinamide  ,Glycerin", ["Water", "Niacinamide", "Glycerin"]),
        ("  Water  ,  Niacinamide  ", ["Water", "Niacinamide"]),
        ("Water\nNiacinamide\nGlycerin", ["Water", "Niacinamide", "Glycerin"]),
        ("Water; Niacinamide; Glycerin", ["Water", "Niacinamide", "Glycerin"]),
        ("Water / Aqua / Eau, Niacinamide, Glycerin", ["Water", "Aqua", "Eau", "Niacinamide", "Glycerin"]),
        ("Niacinamide.", ["Niacinamide"]),
        ("Water,, Niacinamide", ["Water", "Niacinamide"]),  # empty chunk between delimiters
        ("Water,   , Niacinamide", ["Water", "Niacinamide"]),  # whitespace-only chunk
        ("", []),
        ("   ", []),
        (",,,", []),
        (" / / ", []),
        (None, []),
        ("Retinol  Palmitate", ["Retinol Palmitate"]),  # internal whitespace collapsed, not split
    ],
)
def test_parse_ingredient_list(raw_text: str | None, expected: list[str]) -> None:
    assert parse_ingredient_list(raw_text) == expected


def test_parse_ingredient_list_preserves_original_casing_and_wording() -> None:
    tokens = parse_ingredient_list("RETINOL, Niacinamide, glycerin")
    assert tokens == ["RETINOL", "Niacinamide", "glycerin"]


def test_parse_ingredient_list_is_deterministic() -> None:
    text = "Water, Niacinamide, Glycerin, Panthenol, Retinol"
    assert parse_ingredient_list(text) == parse_ingredient_list(text)


def test_parse_ingredient_list_does_not_invent_ingredients() -> None:
    """The parser must never add tokens beyond what was in the input."""
    tokens = parse_ingredient_list("Water, Niacinamide")
    assert len(tokens) == 2
    assert "Glycerin" not in tokens
