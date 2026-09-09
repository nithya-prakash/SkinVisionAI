"""Internal typed representations of the versioned rule files.

Distinct from ``app.schemas.ingredient`` (the public API contract) so the
on-disk file format can evolve independently of the API response shape.
Loaded and validated once by ``rules.py`` -- a rule file that doesn't
match these models fails loudly (raises), never silently.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ingredient import IngredientCategory, RuleSeverity


class AliasesIngredientEntry(BaseModel):
    """One canonical ingredient's entry in aliases.json."""

    model_config = ConfigDict(extra="forbid")

    canonical_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class AliasesFile(BaseModel):
    """The full contents of rules/ingredients/aliases.json."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    last_updated: date
    ingredients: list[AliasesIngredientEntry]
    # alias -> two or more candidate canonical ingredients; deliberately
    # NOT resolved automatically -- see docs/ingredients.md.
    ambiguous_aliases: dict[str, list[str]] = Field(default_factory=dict)


class CategoriesFile(BaseModel):
    """The full contents of rules/ingredients/categories.json:
    category -> list of canonical ingredient names belonging to it.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    categories: dict[IngredientCategory, list[str]]


class CompatibilityRule(BaseModel):
    """One rule entry in rules/ingredients/compatibility.json.

    ``source``/``source_url``/``reason``/``last_verified`` are required --
    an unsourced rule is not accepted (see docs/ingredients.md's source
    policy). ``no_known_conflict`` is refused here: it is only ever
    produced dynamically by the compatibility engine when nothing matches,
    never stored as an authored rule.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    ingredient_a: str = Field(min_length=1)
    ingredient_b: str = Field(min_length=1)
    severity: RuleSeverity
    message: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    last_verified: date
    conditions: str | None = None
    notes: str | None = None

    @field_validator("severity")
    @classmethod
    def _reject_no_known_conflict(cls, value: RuleSeverity) -> RuleSeverity:
        if value == RuleSeverity.NO_KNOWN_CONFLICT:
            raise ValueError(
                "'no_known_conflict' cannot be authored in a rule file -- it is "
                "produced dynamically only when no rule matches a queried pair"
            )
        return value

    @field_validator("source_url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError(f"source_url must be an http(s) URL, got: {value!r}")
        return value


class CompatibilityFile(BaseModel):
    """The full contents of rules/ingredients/compatibility.json."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    last_updated: date
    rules: list[CompatibilityRule]
