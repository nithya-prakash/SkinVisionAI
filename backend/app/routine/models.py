"""Internal typed representations of the versioned routine rule files.

Distinct from ``app.schemas.routine`` (the public API contract), mirroring
the same split ``app.ingredients.models`` makes for the ingredient engine.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import ProductCategory
from app.schemas.ingredient import IngredientCategory


def _validate_http_url(value: str) -> str:
    if not (value.startswith("https://") or value.startswith("http://")):
        raise ValueError(f"source_url must be an http(s) URL, got: {value!r}")
    return value


class OrderingStepEntry(BaseModel):
    """One product category's position within an AM or PM sequence."""

    model_config = ConfigDict(extra="forbid")

    category: ProductCategory
    step_order: int = Field(ge=0)


class OrderingFile(BaseModel):
    """The full contents of rules/routine/ordering.json.

    Carries one shared source citation for the whole ordering methodology
    (a single coherent "how to sequence a routine" claim), rather than one
    citation per category -- see docs/routine.md.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    last_updated: date
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    last_verified: date
    reason: str = Field(min_length=1)
    am_steps: list[OrderingStepEntry]
    pm_steps: list[OrderingStepEntry]

    @field_validator("source_url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        return _validate_http_url(value)


class OverlapFile(BaseModel):
    """The full contents of rules/routine/overlap.json: which ingredient
    categories count as "actives" for duplicate-active detection, plus the
    sourced message/reason shown when an overlap is found.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    last_updated: date
    source: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    last_verified: date
    message: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    active_categories: list[IngredientCategory]

    @field_validator("source_url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        return _validate_http_url(value)
