"""Tests for app.vision.preprocessing."""
from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app.vision.preprocessing import normalize_orientation, resize_for_analysis, to_bgr_array
from tests.helpers.images import make_acceptable_image


def test_normalize_orientation_returns_none_when_no_exif() -> None:
    image = make_acceptable_image(200, 200)
    oriented, orientation = normalize_orientation(image)
    assert orientation is None
    assert oriented.size == (200, 200)


def test_normalize_orientation_reads_and_applies_rotation_tag() -> None:
    image = make_acceptable_image(300, 200)  # landscape
    exif = Image.Exif()
    exif[274] = 6  # rotate 90 CW
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    reloaded = Image.open(buf)

    oriented, orientation = normalize_orientation(reloaded)
    assert orientation == 6
    # A 90-degree rotation swaps width/height.
    assert oriented.size == (200, 300)


def test_resize_for_analysis_downscales_large_images() -> None:
    image = make_acceptable_image(2000, 1000)
    resized = resize_for_analysis(image, max_dimension=1000)
    assert max(resized.size) == 1000
    assert resized.size[0] / resized.size[1] == pytest.approx(2000 / 1000, rel=1e-6)


def test_resize_for_analysis_leaves_small_images_unchanged() -> None:
    image = make_acceptable_image(400, 300)
    resized = resize_for_analysis(image, max_dimension=1000)
    assert resized.size == (400, 300)


def test_resize_for_analysis_never_upscales() -> None:
    image = make_acceptable_image(400, 300)
    resized = resize_for_analysis(image, max_dimension=2000)
    assert resized.size == (400, 300)


def test_resize_for_analysis_boundary_exact_max_dimension_unchanged() -> None:
    image = make_acceptable_image(1000, 500)
    resized = resize_for_analysis(image, max_dimension=1000)
    assert resized.size == (1000, 500)


def test_to_bgr_array_shape_and_channel_order() -> None:
    image = Image.fromarray(np.full((10, 20, 3), (10, 20, 30), dtype=np.uint8))  # RGB
    bgr = to_bgr_array(image)
    assert bgr.shape == (10, 20, 3)
    # RGB (10,20,30) -> BGR (30,20,10)
    assert tuple(int(c) for c in bgr[0, 0]) == (30, 20, 10)
