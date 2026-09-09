"""Runs the routine evaluation dataset against the real Phase 5
deterministic engine (app.routine.analyzer) -- never a second, parallel
implementation of overlap/ordering/compatibility logic.
"""
from __future__ import annotations

from app.routine.analyzer import analyze_routine
from app.schemas.routine import RoutineAnalysisRequest, RoutineProductInput
from evaluation.datasets.routine import DETERMINISM_CASE_PRODUCTS, ROUTINE_CASES, RoutineProduct
from evaluation.metrics import assert_deterministic
from evaluation.runners.base import EvalResult, require_non_empty, require_unique_case_ids

SUBSYSTEM = "routine"


def _to_request(products: tuple[RoutineProduct, ...]) -> RoutineAnalysisRequest:
    return RoutineAnalysisRequest(
        products=[
            RoutineProductInput(
                product_name=p.product_name,
                raw_ingredients=p.raw_ingredients,
                category=p.category,
                time_of_day=p.time_of_day,
            )
            for p in products
        ]
    )


def _run_cases() -> list[EvalResult]:
    require_non_empty(list(ROUTINE_CASES), "routine.ROUTINE_CASES")
    require_unique_case_ids([c.case_id for c in ROUTINE_CASES], "routine.ROUTINE_CASES")

    results: list[EvalResult] = []
    for case in ROUTINE_CASES:
        result = analyze_routine(_to_request(case.products))
        failures = []

        overlap_ingredients = {o.ingredient for o in result.overlapping_actives}
        missing_overlap = case.expect_overlap_ingredients - overlap_ingredients
        if missing_overlap:
            failures.append(f"expected overlap ingredient(s) {sorted(missing_overlap)} not found")

        interaction_rule_ids = {i.rule_id for i in result.interactions if i.rule_id}
        missing_rules = case.expect_interaction_rule_ids - interaction_rule_ids
        if missing_rules:
            failures.append(f"expected interaction rule(s) {sorted(missing_rules)} not found")

        if case.expect_am_order:
            actual_am = tuple(s.product_name for s in result.suggested_am)
            if actual_am != case.expect_am_order:
                failures.append(f"AM order: expected {case.expect_am_order}, got {actual_am}")

        if case.expect_pm_order:
            actual_pm = tuple(s.product_name for s in result.suggested_pm)
            if actual_pm != case.expect_pm_order:
                failures.append(f"PM order: expected {case.expect_pm_order}, got {actual_pm}")

        unscheduled_names = {u.product_name for u in result.unscheduled_products}
        missing_unscheduled = case.expect_unscheduled - unscheduled_names
        if missing_unscheduled:
            failures.append(f"expected {sorted(missing_unscheduled)} to be unscheduled, but they were placed")

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                actual={
                    "overlap_ingredients": sorted(overlap_ingredients),
                    "interaction_rule_ids": sorted(interaction_rule_ids),
                    "am_order": [s.product_name for s in result.suggested_am],
                    "pm_order": [s.product_name for s in result.suggested_pm],
                    "unscheduled": sorted(unscheduled_names),
                },
            )
        )
    return results


def _run_determinism_case() -> EvalResult:
    def compute() -> tuple:
        result = analyze_routine(_to_request(DETERMINISM_CASE_PRODUCTS))
        return (
            tuple(sorted(o.ingredient for o in result.overlapping_actives)),
            tuple(sorted(i.rule_id for i in result.interactions if i.rule_id)),
            tuple(s.product_name for s in result.suggested_am),
            tuple(s.product_name for s in result.suggested_pm),
            tuple(sorted(u.product_name for u in result.unscheduled_products)),
        )

    ok, message = assert_deterministic(compute, repeats=3)
    return EvalResult(
        SUBSYSTEM,
        "routine_analysis_is_deterministic",
        "The same multi-product routine analyzed 3 times produces an identical result",
        passed=ok,
        message=message,
    )


def run() -> list[EvalResult]:
    results = _run_cases()
    results.append(_run_determinism_case())
    return results
