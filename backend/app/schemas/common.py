"""Shared enums and primitives used across multiple schema modules."""
from __future__ import annotations

from enum import StrEnum


class ProductCategory(StrEnum):
    """Broad product categories used for routine placement and comparison."""

    CLEANSER = "cleanser"
    TONER = "toner"
    SERUM = "serum"
    MOISTURIZER = "moisturizer"
    SUNSCREEN = "sunscreen"
    EXFOLIANT = "exfoliant"
    TREATMENT = "treatment"
    OTHER = "other"


class TimeOfDay(StrEnum):
    """When a single, concretely scheduled routine item is applied."""

    AM = "AM"
    PM = "PM"


class TimeOfDayPreference(StrEnum):
    """A product's usage-time preference for routine analysis (Phase 5).

    Distinct from ``TimeOfDay`` (a single scheduled slot): this describes
    the user's stated intent for an ad-hoc product, which may genuinely be
    both times or not stated at all. ``UNSPECIFIED`` is the default --
    the routine engine never invents a schedule for it (with one narrow,
    documented exception for sunscreen; see docs/routine.md).
    """

    AM = "AM"
    PM = "PM"
    AM_AND_PM = "AM_AND_PM"
    UNSPECIFIED = "unspecified"


DISCLAIMER: str = (
    "SkinVision AI provides educational skincare insights, not medical "
    "diagnosis or medical advice."
)
