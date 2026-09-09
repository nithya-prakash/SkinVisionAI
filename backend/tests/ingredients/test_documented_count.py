"""Guards against a documentation-drift bug that already happened once:
README.md and docs/ingredients.md stated "27 canonical ingredients"
while aliases.json actually defined 28. This derives the authoritative
count from the real rule data (never a hardcoded expected number) and
cross-checks it against every doc that states a count, so a future
ingredient addition/removal without a doc update fails the suite
instead of drifting silently.

Skips (rather than fails) when the repository root isn't reachable --
the backend Docker build context only copies backend/, so README.md and
docs/ don't exist inside the api container. The check still runs for a
local `pytest` from a full checkout and is the source of truth there.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ingredients.rules import get_rule_set

_COUNT_PATTERN = re.compile(r"(\d+)\s+canonical ingredients")
_DOC_FILES = ("README.md", "docs/ingredients.md")


def _find_repo_root() -> Path | None:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "README.md").is_file() and (candidate / "docs").is_dir():
            return candidate
    return None


def test_documented_ingredient_count_matches_rule_data() -> None:
    actual_count = len(get_rule_set().canonical_names)

    repo_root = _find_repo_root()
    if repo_root is None:
        pytest.skip("repository root (README.md/docs/) not present in this build context")

    for relative_path in _DOC_FILES:
        text = (repo_root / relative_path).read_text()
        documented_counts = {int(match) for match in _COUNT_PATTERN.findall(text)}
        assert documented_counts, f"{relative_path} no longer states a canonical ingredient count"
        assert documented_counts == {actual_count}, (
            f"{relative_path} claims {sorted(documented_counts)} canonical "
            f"ingredient(s), but aliases.json actually defines {actual_count}"
        )
