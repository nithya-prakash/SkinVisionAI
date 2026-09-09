"""Tests for app.vision.region.

Face-box selection logic (margin expansion, clipping, largest-of-multiple)
is tested against a *mocked* cascade detector so it's deterministic and
doesn't depend on an actual face appearing in a synthetic image. A separate
smoke test exercises the real bundled Haar cascade against a non-face
synthetic image to confirm the "no face detected" fallback path actually
works end-to-end.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.schemas.vision import RegionSource
from app.vision import region as region_module
from app.vision.region import RegionThresholds, detect_region

DEFAULT_THRESHOLDS = RegionThresholds(
    face_min_size_fraction=0.15, face_margin_fraction=0.25, center_crop_fraction=0.6
)


class _FakeCascade:
    def __init__(self, detections: list[tuple[int, int, int, int]]) -> None:
        self._detections = np.array(detections, dtype=np.int32) if detections else np.array([])

    def detectMultiScale(self, *args, **kwargs):  # noqa: N802 -- matches cv2's API
        return self._detections


@pytest.fixture(autouse=True)
def _clear_cascade_cache():
    region_module._load_face_cascade.cache_clear()
    yield
    region_module._load_face_cascade.cache_clear()


def test_no_faces_falls_back_to_center_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(region_module, "_load_face_cascade", lambda: _FakeCascade([]))
    gray = np.zeros((800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    assert result.source == RegionSource.CENTER_CROP_FALLBACK
    assert result.faces_detected == 0
    x1, y1, x2, y2 = result.box
    assert x2 - x1 == y2 - y1  # square crop
    assert 0 <= x1 < x2 <= 800
    assert 0 <= y1 < y2 <= 800


def test_center_crop_is_centered() -> None:
    box = region_module._center_crop_box(800, 800, 0.6)
    x1, y1, x2, y2 = box
    width = x2 - x1
    assert width == 480  # 800 * 0.6
    assert x1 == (800 - width) // 2
    assert y1 == (800 - width) // 2


def test_single_face_is_expanded_by_margin_and_clipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 100x100 face at (350, 350) in an 800x800 image.
    monkeypatch.setattr(
        region_module, "_load_face_cascade", lambda: _FakeCascade([(350, 350, 100, 100)])
    )
    gray = np.zeros((800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    assert result.source == RegionSource.DETECTED_FACE
    assert result.faces_detected == 1
    x1, y1, x2, y2 = result.box
    # Margin is 25% of 100px = 25px on each side.
    assert x1 == 350 - 25
    assert y1 == 350 - 25
    assert x2 == 350 + 100 + 25
    assert y2 == 350 + 100 + 25


def test_face_near_edge_is_clipped_to_image_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Face touching the top-left corner -- margin expansion would go negative.
    monkeypatch.setattr(
        region_module, "_load_face_cascade", lambda: _FakeCascade([(0, 0, 100, 100)])
    )
    gray = np.zeros((800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    x1, y1, x2, y2 = result.box
    assert x1 == 0
    assert y1 == 0
    assert x2 == 125  # 100 + 25 margin, not clipped on this side
    assert y2 == 125


def test_multiple_faces_picks_the_largest_and_reports_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detections = [
        (50, 50, 80, 80),  # area 6400 (smaller)
        (400, 400, 150, 150),  # area 22500 (largest)
        (600, 100, 90, 90),  # area 8100
    ]
    monkeypatch.setattr(region_module, "_load_face_cascade", lambda: _FakeCascade(detections))
    gray = np.zeros((800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    assert result.source == RegionSource.DETECTED_FACE
    assert result.faces_detected == 3
    x1, y1, x2, y2 = result.box
    # The largest face (400,400,150,150) expanded by 25% margin (37.5 -> 38 rounded).
    assert x1 == 400 - round(150 * 0.25)
    assert y1 == 400 - round(150 * 0.25)


def test_degenerate_box_falls_back_to_center_crop(monkeypatch: pytest.MonkeyPatch) -> None:
    # A detection whose expanded box would still be smaller than the
    # minimum usable region dimension -- exercise the safety fallback.
    monkeypatch.setattr(
        region_module,
        "_load_face_cascade",
        lambda: _FakeCascade([(10, 10, 5, 5)]),
    )
    gray = np.zeros((800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    assert result.source == RegionSource.CENTER_CROP_FALLBACK
    assert result.faces_detected == 1  # a face WAS seen, just unusable


def test_real_cascade_falls_back_on_non_face_synthetic_image() -> None:
    """End-to-end smoke test with the actual bundled Haar cascade (not
    mocked): random noise should never be detected as a face.
    """
    rng = np.random.default_rng(3)
    gray = rng.integers(0, 256, size=(800, 800), dtype=np.uint8)

    result = detect_region(gray, DEFAULT_THRESHOLDS)

    assert result.source == RegionSource.CENTER_CROP_FALLBACK
    assert result.faces_detected == 0
