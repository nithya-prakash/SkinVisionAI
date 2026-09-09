"""Shared JSON rule-file loading, used by both the ingredient engine
(Phase 4) and the routine engine (Phase 5) so this bit of I/O isn't
duplicated across them.
"""
from __future__ import annotations

import json
from pathlib import Path


class RuleLoadError(Exception):
    """Raised when a rule file is missing, malformed, or fails validation.

    Shared across every rule-loading module (ingredients, routine) so
    callers can catch one exception type regardless of which engine's
    rules failed to load.
    """


def read_json_rule_file(path: Path) -> dict:
    """Read and parse one JSON rule file, raising ``RuleLoadError`` (never
    silently skipping) if it's missing or malformed.
    """
    if not path.exists():
        raise RuleLoadError(f"Rule file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuleLoadError(f"Malformed JSON in {path}: {exc}") from exc
