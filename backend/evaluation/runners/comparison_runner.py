"""Runs the product-comparison evaluation dataset against the real
Phase 5 comparator (app.products.comparator) -- never a second, parallel
implementation.
"""
from __future__ import annotations

from app.products.comparator import compare_products
from app.schemas.product import ProductCompareItem, ProductCompareRequest, ProductComparisonResult
from evaluation.datasets.comparison import COMPARISON_CASES, DETERMINISM_CASE, ComparisonProduct
from evaluation.metrics import assert_deterministic
from evaluation.runners.base import EvalResult, require_non_empty, require_unique_case_ids

SUBSYSTEM = "comparison"

# Field names that would indicate a "better product" score/winner --
# the architecture intentionally never defines one (see
# docs/ingredients.md's wording policy). Checked structurally against
# the actual Pydantic schema, not by scanning example output.
_FORBIDDEN_FIELD_SUBSTRINGS = ("score", "winner", "rating", "better", "recommend", "rank")


def _to_request(a: ComparisonProduct, b: ComparisonProduct) -> ProductCompareRequest:
    return ProductCompareRequest(
        product_a=ProductCompareItem(name=a.name, category=a.category, raw_ingredient_text=a.raw_ingredient_text),
        product_b=ProductCompareItem(name=b.name, category=b.category, raw_ingredient_text=b.raw_ingredient_text),
    )


def _run_cases() -> list[EvalResult]:
    require_non_empty(list(COMPARISON_CASES), "comparison.COMPARISON_CASES")
    require_unique_case_ids([c.case_id for c in COMPARISON_CASES], "comparison.COMPARISON_CASES")

    results: list[EvalResult] = []
    for case in COMPARISON_CASES:
        result = compare_products(_to_request(case.product_a, case.product_b))
        failures = []

        shared = set(result.shared_ingredients)
        only_a = set(result.only_in_a)
        only_b = set(result.only_in_b)
        rule_ids = {i.rule_id for i in result.interactions if i.rule_id}
        unknown_a = set(result.unknown_ingredients_a)
        unknown_b = set(result.unknown_ingredients_b)

        # Every expect_* field is None when this case makes no claim
        # about it, vs. an explicit frozenset() when it specifically
        # asserts emptiness -- see ComparisonCase's docstring.
        if case.expect_shared is not None and shared != case.expect_shared:
            failures.append(f"shared: expected {sorted(case.expect_shared)}, got {sorted(shared)}")
        if case.expect_only_in_a is not None and only_a != case.expect_only_in_a:
            failures.append(f"only_in_a: expected {sorted(case.expect_only_in_a)}, got {sorted(only_a)}")
        if case.expect_only_in_b is not None and only_b != case.expect_only_in_b:
            failures.append(f"only_in_b: expected {sorted(case.expect_only_in_b)}, got {sorted(only_b)}")
        if case.expect_interaction_rule_ids is not None:
            missing_rules = case.expect_interaction_rule_ids - rule_ids
            if missing_rules:
                failures.append(f"expected interaction rule(s) {sorted(missing_rules)} not found")
        if case.expect_unknown_a is not None and unknown_a != case.expect_unknown_a:
            failures.append(f"unknown_a: expected {sorted(case.expect_unknown_a)}, got {sorted(unknown_a)}")
        if case.expect_unknown_b is not None and unknown_b != case.expect_unknown_b:
            failures.append(f"unknown_b: expected {sorted(case.expect_unknown_b)}, got {sorted(unknown_b)}")

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=not failures,
                message="; ".join(failures),
                actual={
                    "shared": sorted(shared),
                    "only_in_a": sorted(only_a),
                    "only_in_b": sorted(only_b),
                    "interaction_rule_ids": sorted(rule_ids),
                    "unknown_a": sorted(unknown_a),
                    "unknown_b": sorted(unknown_b),
                },
            )
        )
    return results


def _run_no_score_field_case() -> EvalResult:
    """Structural check: ProductComparisonResult must never grow a
    score/winner/rating field, since this architecture deliberately does
    not define a "better product" -- see docs/ingredients.md.
    """
    field_names = set(ProductComparisonResult.model_fields.keys())
    offending = [
        name for name in field_names if any(bad in name.lower() for bad in _FORBIDDEN_FIELD_SUBSTRINGS)
    ]
    return EvalResult(
        SUBSYSTEM,
        "comparison_never_produces_a_better_product_score",
        "ProductComparisonResult has no score/winner/rating/recommend/rank field",
        passed=not offending,
        message="" if not offending else f"found forbidden-looking field(s): {offending}",
        actual=sorted(field_names),
    )


def _run_determinism_case() -> EvalResult:
    def compute() -> tuple:
        result = compare_products(_to_request(DETERMINISM_CASE.product_a, DETERMINISM_CASE.product_b))
        return (
            tuple(sorted(result.shared_ingredients)),
            tuple(sorted(result.only_in_a)),
            tuple(sorted(result.only_in_b)),
            tuple(sorted(i.rule_id for i in result.interactions if i.rule_id)),
        )

    ok, message = assert_deterministic(compute, repeats=3)
    return EvalResult(
        SUBSYSTEM,
        "comparison_is_deterministic",
        "The same product pair compared 3 times produces an identical result",
        passed=ok,
        message=message,
    )


def run() -> list[EvalResult]:
    results = _run_cases()
    results.append(_run_no_score_field_case())
    results.append(_run_determinism_case())
    return results
