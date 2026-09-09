"""Shared enums and primitives used across multiple schema modules."""
from __future__ import annotations

from enum import StrEnum


class SkinGoal(StrEnum):
    """Self-reported skincare goals a user may select (multi-select)."""

    HYDRATION = "hydration"
    OIL_CONTROL = "oil_control"
    TEXTURE = "texture"
    UNEVEN_TONE = "uneven_tone"
    REDNESS = "redness"
    ANTI_AGING = "anti_aging"
    BARRIER_SUPPORT = "barrier_support"
    GENERAL_SKINCARE = "general_skincare"


class SkinType(StrEnum):
    """Self-reported skin type. Never treated as a medical classification."""

    DRY = "dry"
    OILY = "oily"
    COMBINATION = "combination"
    NORMAL = "normal"
    UNKNOWN = "unknown"


class RoutineFrequency(StrEnum):
    """How often the user says they follow a skincare routine."""

    DAILY = "daily"
    FEW_TIMES_A_WEEK = "few_times_a_week"
    WEEKLY = "weekly"
    OCCASIONALLY = "occasionally"
    RARELY = "rarely"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class SensitivityPreference(StrEnum):
    """Self-reported sensitivity considerations for product recommendations."""

    FRAGRANCE_FREE = "fragrance_free"
    ALCOHOL_FREE = "alcohol_free"
    ESSENTIAL_OIL_FREE = "essential_oil_free"
    LOW_IRRITATION_PRIORITY = "low_irritation_priority"
    NONE = "none"


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
