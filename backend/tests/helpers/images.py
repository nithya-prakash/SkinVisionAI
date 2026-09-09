"""Synthetic test image generators.

Every image used in this test suite is procedurally generated with
NumPy/Pillow. No real photographs -- personal, skin, or otherwise -- are
used anywhere in this repository.
"""
from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageFilter


def _noisy_array(
    width: int, height: int, base: int, spread: int, seed: int = 42
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.integers(-spread, spread + 1, size=(height, width, 3))
    return np.clip(base + noise, 0, 255).astype(np.uint8)


def make_sharp_image(width: int = 800, height: int = 800) -> Image.Image:
    """High-frequency noise -> high Laplacian variance -> reads as 'sharp'."""
    return Image.fromarray(_noisy_array(width, height, base=128, spread=90))


def make_blurry_image(width: int = 800, height: int = 800) -> Image.Image:
    """Same base content as make_sharp_image, heavily Gaussian-blurred."""
    sharp = make_sharp_image(width, height)
    return sharp.filter(ImageFilter.GaussianBlur(radius=14))


def make_dark_image(width: int = 800, height: int = 800) -> Image.Image:
    return Image.fromarray(_noisy_array(width, height, base=10, spread=8))


def make_bright_image(width: int = 800, height: int = 800) -> Image.Image:
    return Image.fromarray(_noisy_array(width, height, base=248, spread=6))


def make_low_contrast_image(width: int = 800, height: int = 800) -> Image.Image:
    return Image.fromarray(_noisy_array(width, height, base=128, spread=3))


def make_tiny_image(width: int = 50, height: int = 50) -> Image.Image:
    return Image.fromarray(_noisy_array(width, height, base=128, spread=60))


def make_acceptable_image(width: int = 800, height: int = 800) -> Image.Image:
    """An image expected to pass every quality check under the default thresholds."""
    return make_sharp_image(width, height)


def to_bytes(image: Image.Image, fmt: str = "JPEG", quality: int = 92) -> bytes:
    buf = io.BytesIO()
    save_kwargs = {"quality": quality} if fmt == "JPEG" else {}
    image.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def corrupted_jpeg_bytes(width: int = 400, height: int = 400) -> bytes:
    """A truncated JPEG -- enough of a header to look plausible, not enough
    to decode successfully.
    """
    good = to_bytes(make_acceptable_image(width, height), "JPEG")
    return good[: len(good) // 3]


def not_an_image_bytes() -> bytes:
    """Plain text bytes, for the 'fake image with an image MIME type' case."""
    return b"this is definitely not image data" * 20


def decompression_bomb_png_bytes(declared_width: int = 100_000, declared_height: int = 100_000) -> bytes:
    """A tiny, structurally valid 1x1 PNG whose IHDR chunk is rewritten to
    declare an enormous width/height (Phase 10).

    Pillow's decompression-bomb guard (``Image.MAX_IMAGE_PIXELS``) fires
    off the *declared* header size as soon as the file is opened, before
    any real pixel data is decoded -- so this file is only a few dozen
    bytes on disk, not an actual multi-gigabyte image, while still
    triggering exactly the check a genuinely malicious upload would.
    """
    import struct
    import zlib

    tiny = Image.new("RGB", (1, 1))
    buf = io.BytesIO()
    tiny.save(buf, format="PNG")
    png_bytes = bytearray(buf.getvalue())

    sig_len = 8
    length = struct.unpack(">I", png_bytes[sig_len : sig_len + 4])[0]
    assert png_bytes[sig_len + 4 : sig_len + 8] == b"IHDR"
    ihdr_data_start = sig_len + 8

    new_ihdr_data = (
        struct.pack(">I", declared_width)
        + struct.pack(">I", declared_height)
        + png_bytes[ihdr_data_start + 8 : ihdr_data_start + length]
    )
    crc = zlib.crc32(b"IHDR" + new_ihdr_data) & 0xFFFFFFFF

    return bytes(
        png_bytes[:ihdr_data_start]
        + bytearray(new_ihdr_data)
        + bytearray(struct.pack(">I", crc))
        + png_bytes[ihdr_data_start + length + 4 :]
    )


# --- Phase 3: visual-observation pipeline fixtures ---
# All RGB (PIL order); helpers that build via OpenCV convert BGR -> RGB
# before wrapping in a PIL Image, so callers always get standard RGB.


def make_uniform_image(
    width: int = 800, height: int = 800, color: tuple[int, int, int] = (150, 130, 120)
) -> Image.Image:
    """A single flat color, no noise, no structure -- the baseline case."""
    array = np.full((height, width, 3), color, dtype=np.uint8)
    return Image.fromarray(array)


def make_red_tinted_image(width: int = 800, height: int = 800) -> Image.Image:
    """Uniform, strongly red-shifted color -- an artificial 'red region'
    covering the whole frame, so redness detection isn't sensitive to
    exactly where the region-of-interest crop lands.
    """
    array = np.full((height, width, 3), (200, 90, 90), dtype=np.uint8)
    return Image.fromarray(array)


def make_textured_image(width: int = 800, height: int = 800) -> Image.Image:
    """Alias of make_sharp_image: dense per-pixel noise on a neutral base,
    i.e. artificial fine texture.
    """
    return make_sharp_image(width, height)


def make_highlight_image(width: int = 800, height: int = 800) -> Image.Image:
    """A neutral base with a bright, low-saturation patch -- an artificial
    specular highlight covering a known fraction of the frame.
    """
    array = np.full((height, width, 3), (130, 120, 115), dtype=np.uint8)
    patch_h, patch_w = height // 4, width // 4
    y0, x0 = height // 2 - patch_h // 2, width // 2 - patch_w // 2
    array[y0 : y0 + patch_h, x0 : x0 + patch_w] = (250, 248, 250)
    return Image.fromarray(array)


def make_color_variation_image(width: int = 800, height: int = 800) -> Image.Image:
    """A smooth top-to-bottom lightness gradient: high tone variation
    (Lab L* std) without the high-frequency noise that would also read as
    'texture' -- isolating the uneven-tone signal for testing.
    """
    gradient = np.linspace(60, 220, height, dtype=np.uint8)
    array = np.tile(gradient[:, None, None], (1, width, 3))
    return Image.fromarray(array.astype(np.uint8))


def make_spotted_image(
    width: int = 800, height: int = 800, spot_count: int = 8, radius: int = 6
) -> Image.Image:
    """A neutral base with a fixed number of small, deliberately placed
    dark circular marks -- artificial 'visible spots/marks'.

    Marks are placed within the image's central 60% (matching the vision
    pipeline's default no-face-detected fallback crop) so pipeline-level
    tests actually see every planted mark rather than losing some outside
    the analyzed region.
    """
    array = np.full((height, width, 3), (150, 135, 125), dtype=np.uint8)
    rng = np.random.default_rng(7)
    x_lo, x_hi = round(width * 0.25), round(width * 0.75)
    y_lo, y_hi = round(height * 0.25), round(height * 0.75)
    for _ in range(spot_count):
        cx = int(rng.integers(x_lo, x_hi))
        cy = int(rng.integers(y_lo, y_hi))
        cv2.circle(array, (cx, cy), radius, (60, 50, 45), thickness=-1)
    return Image.fromarray(array)
