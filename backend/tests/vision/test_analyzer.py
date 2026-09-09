"""Tests for app.vision.analyzer -- the full Phase 3 pipeline.

Verifies pipeline wiring, determinism, the dryness-omission policy, and the
non-diagnostic safety boundary. Does NOT and cannot verify real-world skin
analysis accuracy -- see docs/vision.md's explicit testing-limitation note.
"""
from __future__ import annotations

from app.config import Settings
from app.schemas.vision import ObservationFeature, RegionSource
from app.vision.analyzer import DRYNESS_LIMITATION, run_visual_analysis
from tests.helpers.images import (
    make_color_variation_image,
    make_highlight_image,
    make_red_tinted_image,
    make_spotted_image,
    make_textured_image,
    make_uniform_image,
)

SETTINGS = Settings()
ALL_FEATURES = {
    ObservationFeature.REDNESS,
    ObservationFeature.VISIBLE_TEXTURE,
    ObservationFeature.SHINE_OILINESS,
    ObservationFeature.UNEVEN_TONE,
    ObservationFeature.VISIBLE_SPOTS_MARKS,
}


def test_pipeline_produces_exactly_the_five_estimable_features() -> None:
    result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    features = {obs.feature for obs in result.observations}
    assert features == ALL_FEATURES


def test_dryness_is_never_emitted_as_an_observation() -> None:
    result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    assert ObservationFeature.DRYNESS not in {obs.feature for obs in result.observations}
    assert DRYNESS_LIMITATION in result.limitations


def test_no_face_in_synthetic_images_uses_center_crop_fallback() -> None:
    result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    assert result.region.source == RegionSource.CENTER_CROP_FALLBACK
    assert any("centered region" in note for note in result.limitations)


def test_red_tinted_image_flags_elevated_redness() -> None:
    result = run_visual_analysis(make_red_tinted_image(), SETTINGS, quality_score=0.9)
    redness = next(o for o in result.observations if o.feature == ObservationFeature.REDNESS)
    assert redness.score > 0.3


def test_textured_image_flags_elevated_texture() -> None:
    result = run_visual_analysis(make_textured_image(), SETTINGS, quality_score=0.9)
    texture = next(
        o for o in result.observations if o.feature == ObservationFeature.VISIBLE_TEXTURE
    )
    uniform_result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    uniform_texture = next(
        o for o in uniform_result.observations if o.feature == ObservationFeature.VISIBLE_TEXTURE
    )
    assert texture.score > uniform_texture.score


def test_highlight_image_flags_elevated_shine() -> None:
    result = run_visual_analysis(make_highlight_image(), SETTINGS, quality_score=0.9)
    shine = next(o for o in result.observations if o.feature == ObservationFeature.SHINE_OILINESS)
    uniform_result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    uniform_shine = next(
        o for o in uniform_result.observations if o.feature == ObservationFeature.SHINE_OILINESS
    )
    assert shine.score >= uniform_shine.score


def test_color_variation_image_flags_elevated_tone_variation() -> None:
    result = run_visual_analysis(make_color_variation_image(), SETTINGS, quality_score=0.9)
    tone = next(o for o in result.observations if o.feature == ObservationFeature.UNEVEN_TONE)
    uniform_result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    uniform_tone = next(
        o for o in uniform_result.observations if o.feature == ObservationFeature.UNEVEN_TONE
    )
    assert tone.score > uniform_tone.score


def test_spotted_image_flags_elevated_spots() -> None:
    result = run_visual_analysis(make_spotted_image(), SETTINGS, quality_score=0.9)
    spots = next(
        o for o in result.observations if o.feature == ObservationFeature.VISIBLE_SPOTS_MARKS
    )
    uniform_result = run_visual_analysis(make_uniform_image(), SETTINGS, quality_score=0.9)
    uniform_spots = next(
        o
        for o in uniform_result.observations
        if o.feature == ObservationFeature.VISIBLE_SPOTS_MARKS
    )
    assert spots.score > uniform_spots.score


def test_pipeline_is_deterministic_given_the_same_image_and_settings() -> None:
    image = make_red_tinted_image()
    first = run_visual_analysis(image, SETTINGS, quality_score=0.85)
    second = run_visual_analysis(image, SETTINGS, quality_score=0.85)

    first_dump = [obs.model_dump() for obs in first.observations]
    second_dump = [obs.model_dump() for obs in second.observations]
    assert first_dump == second_dump
    assert first.limitations == second.limitations
    assert first.region.source == second.region.source


def test_lower_quality_score_yields_lower_confidence() -> None:
    image = make_uniform_image()
    high_quality = run_visual_analysis(image, SETTINGS, quality_score=0.95)
    low_quality = run_visual_analysis(image, SETTINGS, quality_score=0.3)
    assert low_quality.observations[0].confidence < high_quality.observations[0].confidence


def test_confidence_is_never_reported_as_exactly_zero() -> None:
    image = make_uniform_image()
    result = run_visual_analysis(image, SETTINGS, quality_score=0.0)
    for obs in result.observations:
        assert obs.confidence >= 0.1


def test_every_observation_has_a_method_and_no_diagnostic_language() -> None:
    result = run_visual_analysis(make_red_tinted_image(), SETTINGS, quality_score=0.9)
    banned_terms = ("acne", "rosacea", "eczema", "melanoma", "diagnos", "disease", "condition")
    for obs in result.observations:
        assert obs.method
        text = f"{obs.note or ''}".lower()
        for term in banned_terms:
            assert term not in text
    for limitation in result.limitations:
        for term in banned_terms:
            assert term not in limitation.lower()
