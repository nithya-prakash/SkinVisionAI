"""Deterministic AM/PM routine ordering.

Places each input product into a suggested AM and/or PM sequence based on
its (self-reported) category and time-of-day preference, using the
versioned step-order table in ``rules/routine/ordering.json``. Never
fabricates a position for a product whose category is unknown, and never
invents a schedule for a product whose time-of-day preference is
unspecified -- with exactly one narrow, documented exception: a product
explicitly categorized as sunscreen is placed in the AM sequence even
when its time-of-day preference is unspecified, since "sunscreen" is by
definition a daytime-protective product category, not an inferred
property of some ingredient. See docs/routine.md.
"""
from __future__ import annotations

from app.routine.rules import RoutineRuleSet
from app.schemas.common import ProductCategory, TimeOfDayPreference
from app.schemas.routine import RoutineProductInput, ScheduledStep, UnscheduledProduct

_UNKNOWN_CATEGORY_REASON = "Product category is unknown; no routine position can be suggested."
_UNSPECIFIED_TIME_REASON = (
    "Time of day was not specified for this product, so no schedule was suggested."
)


def _no_rule_reason(category: ProductCategory, track: str) -> str:
    return (
        f"No deterministic ordering rule exists for category "
        f"{category.value!r} in the {track} sequence."
    )


def suggest_ordering(
    products: list[RoutineProductInput], rule_set: RoutineRuleSet
) -> tuple[list[ScheduledStep], list[ScheduledStep], list[UnscheduledProduct]]:
    am_steps: list[ScheduledStep] = []
    pm_steps: list[ScheduledStep] = []
    unscheduled: list[UnscheduledProduct] = []

    for product in products:
        category = product.category
        if category is None:
            unscheduled.append(
                UnscheduledProduct(product_name=product.product_name, reason=_UNKNOWN_CATEGORY_REASON)
            )
            continue

        am_order = rule_set.am_step_order.get(category)
        pm_order = rule_set.pm_step_order.get(category)
        placed = False
        reasons: list[str] = []

        wants_am = product.time_of_day in (TimeOfDayPreference.AM, TimeOfDayPreference.AM_AND_PM)
        wants_pm = product.time_of_day in (TimeOfDayPreference.PM, TimeOfDayPreference.AM_AND_PM)

        # The one deterministic, documented exception: an explicitly
        # sunscreen-categorized product is AM by definition, even with no
        # stated time-of-day preference.
        if product.time_of_day == TimeOfDayPreference.UNSPECIFIED and category == ProductCategory.SUNSCREEN:
            wants_am = True

        if wants_am:
            if am_order is not None:
                am_steps.append(
                    ScheduledStep(product_name=product.product_name, category=category, step_order=am_order)
                )
                placed = True
            else:
                reasons.append(_no_rule_reason(category, "AM"))

        if wants_pm:
            if pm_order is not None:
                pm_steps.append(
                    ScheduledStep(product_name=product.product_name, category=category, step_order=pm_order)
                )
                placed = True
            else:
                reasons.append(_no_rule_reason(category, "PM"))

        if not placed:
            if product.time_of_day == TimeOfDayPreference.UNSPECIFIED:
                reasons.append(_UNSPECIFIED_TIME_REASON)
            unscheduled.append(
                UnscheduledProduct(product_name=product.product_name, reason=" ".join(reasons) or _UNSPECIFIED_TIME_REASON)
            )

    am_steps.sort(key=lambda step: (step.step_order, step.product_name))
    pm_steps.sort(key=lambda step: (step.step_order, step.product_name))
    unscheduled.sort(key=lambda item: item.product_name)

    return am_steps, pm_steps, unscheduled
