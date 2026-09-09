"""Vision evaluation fixtures (Phase 11).

Reuses the exact same procedural image generators already used by the
Phase 2/3 unit test suite (``tests.helpers.images``) rather than a second
parallel implementation -- every image here is generated at runtime from
a fixed seed, never a stored binary (consistent with this repo's
``backend/datasets/images/`` being gitignored for exactly this reason:
no real or binary photo content is ever committed).

**Not a clinical accuracy benchmark.** Each fixture is a deliberately
controlled synthetic image (a flat color, isolated high-frequency noise,
a red tint) built to produce one clear, defensible signal for one
feature -- it proves the pipeline responds correctly and *deterministically*
to a known input, never that it is accurate against real skin or any
medical condition. See docs/evaluation.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PIL import Image

from app.schemas.image import ImageQualityIssue
from app.schemas.vision import ObservationFeature, ObservationLevel
from tests.helpers.images import (
    make_acceptable_image,
    make_bright_image,
    make_color_variation_image,
    make_dark_image,
    make_highlight_image,
    make_low_contrast_image,
    make_red_tinted_image,
    make_spotted_image,
    make_textured_image,
    make_tiny_image,
    make_uniform_image,
)

# Heuristic level ordering (see app.schemas.vision.ObservationLevel) --
# used to express "at least this level," never an exact score, matching
# the existing test suite's own convention of checking behavior/direction
# rather than pinning a heuristic score value.
_LEVEL_ORDER = [
    ObservationLevel.MINIMAL,
    ObservationLevel.MILD,
    ObservationLevel.MODERATE,
    ObservationLevel.PRONOUNCED,
]


def level_at_least(actual: ObservationLevel, minimum: ObservationLevel) -> bool:
    return _LEVEL_ORDER.index(actual) >= _LEVEL_ORDER.index(minimum)


def level_at_most(actual: ObservationLevel, maximum: ObservationLevel) -> bool:
    return _LEVEL_ORDER.index(actual) <= _LEVEL_ORDER.index(maximum)


@dataclass(frozen=True)
class QualityCase:
    """A case for the image-quality gate only (app.vision.quality)."""

    case_id: str
    description: str
    image_factory: Callable[[], Image.Image]
    expect_acceptable: bool
    # Issues that MUST all be present when expect_acceptable is False.
    # Ignored when expect_acceptable is True (there, issues must be empty).
    expect_issues: frozenset[ImageQualityIssue] = frozenset()


@dataclass(frozen=True)
class ObservationExpectation:
    feature: ObservationFeature
    min_level: ObservationLevel | None = None
    max_level: ObservationLevel | None = None


@dataclass(frozen=True)
class ObservationCase:
    """A case for the visual-observation pipeline (app.vision.analyzer),
    run against an image assumed to already pass the quality gate.
    """

    case_id: str
    description: str
    image_factory: Callable[[], Image.Image]
    expectations: tuple[ObservationExpectation, ...] = field(default_factory=tuple)


QUALITY_CASES: tuple[QualityCase, ...] = (
    QualityCase(
        case_id="quality_acceptable_baseline",
        description="A sufficiently bright, sharp, well-contrasted image passes every check",
        image_factory=lambda: make_acceptable_image(800, 800),
        expect_acceptable=True,
    ),
    QualityCase(
        case_id="quality_too_dark",
        description="A very dark image is flagged too_dark and rejected",
        image_factory=lambda: make_dark_image(800, 800),
        expect_acceptable=False,
        expect_issues=frozenset({ImageQualityIssue.TOO_DARK}),
    ),
    QualityCase(
        case_id="quality_overexposed",
        description="A very bright image is flagged overexposed and rejected",
        image_factory=lambda: make_bright_image(800, 800),
        expect_acceptable=False,
        expect_issues=frozenset({ImageQualityIssue.OVEREXPOSED}),
    ),
    QualityCase(
        case_id="quality_too_low_resolution",
        description="A low-resolution image is flagged too_low_resolution and rejected",
        image_factory=lambda: make_tiny_image(50, 50),
        expect_acceptable=False,
        expect_issues=frozenset({ImageQualityIssue.TOO_LOW_RESOLUTION}),
    ),
    QualityCase(
        case_id="quality_low_contrast",
        description="A low-contrast image is flagged low_contrast and rejected",
        image_factory=lambda: make_low_contrast_image(800, 800),
        expect_acceptable=False,
        expect_issues=frozenset({ImageQualityIssue.LOW_CONTRAST}),
    ),
)


OBSERVATION_CASES: tuple[ObservationCase, ...] = (
    ObservationCase(
        case_id="observation_uniform_reads_minimal_texture",
        description="A flat, structureless image reads as minimal visible texture",
        image_factory=lambda: make_uniform_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.VISIBLE_TEXTURE, max_level=ObservationLevel.MILD),
        ),
    ),
    ObservationCase(
        case_id="observation_textured_reads_elevated_texture",
        description="Dense high-frequency noise reads as elevated visible texture",
        image_factory=lambda: make_textured_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.VISIBLE_TEXTURE, min_level=ObservationLevel.MODERATE),
        ),
    ),
    ObservationCase(
        case_id="observation_red_tinted_reads_elevated_redness",
        description="A strongly red-shifted image reads as elevated visible redness",
        image_factory=lambda: make_red_tinted_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.REDNESS, min_level=ObservationLevel.MODERATE),
        ),
    ),
    ObservationCase(
        case_id="observation_neutral_gray_reads_minimal_redness",
        description="A neutral gray (non-warm-toned) flat-color image reads as minimal visible redness",
        image_factory=lambda: make_uniform_image(800, 800, color=(140, 140, 140)),
        expectations=(
            ObservationExpectation(ObservationFeature.REDNESS, max_level=ObservationLevel.MILD),
        ),
    ),
    ObservationCase(
        case_id="observation_highlight_reads_elevated_shine",
        description="A bright, low-saturation highlight patch reads as elevated visible shine",
        image_factory=lambda: make_highlight_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.SHINE_OILINESS, min_level=ObservationLevel.MILD),
        ),
    ),
    ObservationCase(
        case_id="observation_color_variation_reads_elevated_uneven_tone",
        description="A smooth lightness gradient reads as elevated uneven tone",
        image_factory=lambda: make_color_variation_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.UNEVEN_TONE, min_level=ObservationLevel.MODERATE),
        ),
    ),
    ObservationCase(
        case_id="observation_uniform_reads_minimal_uneven_tone",
        description="A flat-color image with no gradient reads as minimal uneven tone",
        image_factory=lambda: make_uniform_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.UNEVEN_TONE, max_level=ObservationLevel.MILD),
        ),
    ),
    ObservationCase(
        case_id="observation_spotted_reads_elevated_spots_marks",
        description="An image with 20 deliberately placed dark marks reads as elevated visible spots/marks",
        image_factory=lambda: make_spotted_image(800, 800, spot_count=20, radius=8),
        expectations=(
            ObservationExpectation(ObservationFeature.VISIBLE_SPOTS_MARKS, min_level=ObservationLevel.MODERATE),
        ),
    ),
    ObservationCase(
        case_id="observation_uniform_reads_minimal_spots_marks",
        description="A flat-color image with no marks reads as minimal visible spots/marks",
        image_factory=lambda: make_uniform_image(800, 800),
        expectations=(
            ObservationExpectation(ObservationFeature.VISIBLE_SPOTS_MARKS, max_level=ObservationLevel.MILD),
        ),
    ),
)

# One case reused by the runner's determinism check -- any deterministic,
# acceptable-quality image works; the acceptable baseline is the most
# representative choice.
DETERMINISM_CASE_IMAGE_FACTORY: Callable[[], Image.Image] = lambda: make_acceptable_image(800, 800)
