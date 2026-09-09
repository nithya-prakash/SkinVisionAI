"""Upload validation: content-type + actual-content verification, size
limits, and safe filename handling.

Nothing here trusts the client. The claimed Content-Type header and the
client-supplied filename are both treated as untrusted hints -- the real
image format is always verified by decoding the bytes with Pillow, and the
filename is never used to build a filesystem path (a UUID-based name is
generated for storage instead; see ``app.services.image_service``).
"""
from __future__ import annotations

import re
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

UPLOAD_ACCEPTED_CONTENT_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png"})
UPLOAD_ACCEPTED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG"})

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")
_DEFAULT_FALLBACK_FILENAME = "upload"
_MAX_FILENAME_LENGTH = 255


class UploadValidationError(Exception):
    """A user-correctable upload problem, mapped to an HTTP status by the API route."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def sanitize_filename(raw_name: str | None) -> str:
    """Reduce a client-supplied filename to a safe display-only basename.

    Strips any directory components (defeating ``../`` path traversal),
    drops characters outside a small safe set, and falls back to a generic
    name if nothing usable remains. This value is stored as metadata only
    -- it never participates in constructing a filesystem path.
    """
    if not raw_name:
        return _DEFAULT_FALLBACK_FILENAME

    # Strip any path components regardless of separator style, and cut at
    # the first NUL byte (a classic string-truncation attack vector).
    name = raw_name.replace("\\", "/").split("/")[-1]
    name = name.split("\x00")[0].strip()
    name = _SAFE_FILENAME_RE.sub("_", name)
    name = name.strip("._")

    return (name or _DEFAULT_FALLBACK_FILENAME)[:_MAX_FILENAME_LENGTH]


def validate_upload_size(size_bytes: int, max_size_mb: int) -> None:
    """Raise if the upload is empty or exceeds the configured maximum."""
    if size_bytes <= 0:
        raise UploadValidationError(
            code="empty_file", message="Uploaded file is empty.", status_code=400
        )
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise UploadValidationError(
            code="file_too_large",
            message=f"Image exceeds the maximum allowed size of {max_size_mb}MB.",
            status_code=413,
        )


def validate_content_type(content_type: str | None) -> None:
    """Fast-fail on an unsupported claimed Content-Type, before decoding anything."""
    if content_type not in UPLOAD_ACCEPTED_CONTENT_TYPES:
        raise UploadValidationError(
            code="unsupported_format",
            message=(
                f"Unsupported content type '{content_type}'. "
                "Supported formats: JPEG, PNG."
            ),
            status_code=415,
        )


def load_and_validate_image(raw_bytes: bytes) -> Image.Image:
    """Decode and verify the actual image content.

    This is independent of any client-supplied Content-Type or filename --
    a file that merely claims to be a JPEG (e.g. a renamed text file) is
    caught here, not by trusting the request headers. Raises
    ``UploadValidationError`` for anything that isn't a genuine, intact
    JPEG or PNG. Never includes the raw bytes in any error message or log.

    Also guards against a decompression bomb: a small file whose *decoded*
    pixel count is enormous (Pillow checks this against
    ``Image.MAX_IMAGE_PIXELS`` as soon as it reads the header, i.e. before
    any expensive per-pixel work happens downstream in the vision
    pipeline). Pillow signals this two ways depending on how far over the
    limit the image is: ``DecompressionBombError`` for a large excess, or
    only a ``DecompressionBombWarning`` for a smaller one -- neither is an
    ``OSError``/``ValueError``, so both are caught explicitly here rather
    than falling through to an unhandled 500. The warning is promoted to
    an exception only for the scope of this call (``catch_warnings``),
    never touching the process-wide warning filter.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        try:
            with Image.open(BytesIO(raw_bytes)) as probe:
                probe.verify()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise UploadValidationError(
                code="image_too_large_decoded",
                message="The uploaded image's decoded dimensions exceed the maximum allowed size.",
                status_code=400,
            ) from None
        except (UnidentifiedImageError, OSError, ValueError):
            raise UploadValidationError(
                code="invalid_image_content",
                message="The uploaded file is not a valid image, or the image data is corrupted.",
                status_code=400,
            ) from None

        # Image.verify() invalidates the file object for further use, so
        # the image must be reopened to actually decode pixel data.
        try:
            image = Image.open(BytesIO(raw_bytes))
            image.load()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise UploadValidationError(
                code="image_too_large_decoded",
                message="The uploaded image's decoded dimensions exceed the maximum allowed size.",
                status_code=400,
            ) from None
        except (UnidentifiedImageError, OSError, ValueError):
            raise UploadValidationError(
                code="invalid_image_content",
                message="The uploaded file is not a valid image, or the image data is corrupted.",
                status_code=400,
            ) from None

    if image.format not in UPLOAD_ACCEPTED_FORMATS:
        raise UploadValidationError(
            code="unsupported_format",
            message=f"Unsupported image format '{image.format}'. Supported formats: JPEG, PNG.",
            status_code=415,
        )

    return image
