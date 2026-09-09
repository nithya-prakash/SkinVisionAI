"""Runs the vision evaluation dataset against the real Phase 2/3
deterministic pipeline (app.vision.quality, app.vision.analyzer) --
never a second, parallel implementation of the pipeline's logic.
"""
from __future__ import annotations

from app.config import Settings
from app.vision.analyzer import run_visual_analysis
from app.vision.quality import QualityThresholds, analyze_image_quality
from evaluation.datasets.vision import (
    DETERMINISM_CASE_IMAGE_FACTORY,
    OBSERVATION_CASES,
    QUALITY_CASES,
    level_at_least,
    level_at_most,
)
from evaluation.metrics import assert_deterministic
from evaluation.runners.base import EvalResult, MalformedCaseError, require_non_empty, require_unique_case_ids
from tests.helpers.images import to_bytes

SETTINGS = Settings()
THRESHOLDS = QualityThresholds.from_settings(SETTINGS)

SUBSYSTEM = "vision"


def _run_quality_cases() -> list[EvalResult]:
    require_non_empty(list(QUALITY_CASES), "vision.QUALITY_CASES")
    require_unique_case_ids([c.case_id for c in QUALITY_CASES], "vision.QUALITY_CASES")

    results: list[EvalResult] = []
    for case in QUALITY_CASES:
        image = case.image_factory()
        size_bytes = len(to_bytes(image, "JPEG"))
        result = analyze_image_quality(image, THRESHOLDS, file_size_bytes=size_bytes)

        if result.is_acceptable != case.expect_acceptable:
            results.append(
                EvalResult(
                    SUBSYSTEM,
                    case.case_id,
                    case.description,
                    passed=False,
                    message=(
                        f"expected is_acceptable={case.expect_acceptable}, "
                        f"got {result.is_acceptable} (issues={[i.value for i in result.issues]})"
                    ),
                    expected=case.expect_acceptable,
                    actual=result.is_acceptable,
                )
            )
            continue

        missing = case.expect_issues - set(result.issues)
        if missing:
            results.append(
                EvalResult(
                    SUBSYSTEM,
                    case.case_id,
                    case.description,
                    passed=False,
                    message=f"expected issue(s) {[i.value for i in missing]} not present",
                    expected=[i.value for i in case.expect_issues],
                    actual=[i.value for i in result.issues],
                )
            )
            continue

        results.append(
            EvalResult(
                SUBSYSTEM,
                case.case_id,
                case.description,
                passed=True,
                expected=case.expect_acceptable,
                actual=result.is_acceptable,
            )
        )
    return results


def _run_observation_cases() -> list[EvalResult]:
    require_non_empty(list(OBSERVATION_CASES), "vision.OBSERVATION_CASES")
    require_unique_case_ids([c.case_id for c in OBSERVATION_CASES], "vision.OBSERVATION_CASES")

    results: list[EvalResult] = []
    for case in OBSERVATION_CASES:
        image = case.image_factory()
        size_bytes = len(to_bytes(image, "JPEG"))
        quality = analyze_image_quality(image, THRESHOLDS, file_size_bytes=size_bytes)
        analysis = run_visual_analysis(image, SETTINGS, quality_score=quality.score)
        by_feature = {obs.feature: obs for obs in analysis.observations}

        if not case.expectations:
            raise MalformedCaseError(f"vision case {case.case_id!r} has no expectations to check")

        failures = []
        for exp in case.expectations:
            obs = by_feature.get(exp.feature)
            if obs is None:
                failures.append(f"{exp.feature.value}: no observation produced")
                continue
            if exp.min_level is not None and not level_at_least(obs.level, exp.min_level):
                failures.append(f"{exp.feature.value}: expected >= {exp.min_level.value}, got {obs.level.value}")
            if exp.max_level is not None and not level_at_most(obs.level, exp.max_level):
                failures.append(f"{exp.feature.value}: expected <= {exp.max_level.value}, got {obs.level.value}")

        actual_levels = {f.value: obs.level.value for f, obs in by_feature.items()}
        if failures:
            results.append(
                EvalResult(
                    SUBSYSTEM,
                    case.case_id,
                    case.description,
                    passed=False,
                    message="; ".join(failures),
                    expected={
                        e.feature.value: {
                            "min": e.min_level.value if e.min_level else None,
                            "max": e.max_level.value if e.max_level else None,
                        }
                        for e in case.expectations
                    },
                    actual=actual_levels,
                )
            )
        else:
            results.append(
                EvalResult(SUBSYSTEM, case.case_id, case.description, passed=True, actual=actual_levels)
            )
    return results


def _run_determinism_case() -> EvalResult:
    image = DETERMINISM_CASE_IMAGE_FACTORY()
    size_bytes = len(to_bytes(image, "JPEG"))
    quality = analyze_image_quality(image, THRESHOLDS, file_size_bytes=size_bytes)

    def compute() -> tuple:
        analysis = run_visual_analysis(image, SETTINGS, quality_score=quality.score)
        return tuple((obs.feature.value, obs.level.value, obs.score) for obs in analysis.observations)

    ok, message = assert_deterministic(compute, repeats=3)
    return EvalResult(
        SUBSYSTEM,
        "vision_pipeline_is_deterministic",
        "The same image analyzed 3 times produces byte-identical observation output",
        passed=ok,
        message=message,
    )


def run() -> list[EvalResult]:
    results: list[EvalResult] = []
    results.extend(_run_quality_cases())
    results.extend(_run_observation_cases())
    results.append(_run_determinism_case())
    return results
