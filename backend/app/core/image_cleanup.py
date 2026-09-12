"""Deletes the on-disk bytes of expired ``temporary``-mode uploads.

Closes a previously disclosed gap: an image written under
``IMAGE_RETENTION_MODE=temporary`` used to stay on disk until manually
removed. This module is the deterministic core of that fix -- pure
database + filesystem I/O, no vision/LLM/agent code involved, so it's
unit-testable without any of that machinery.

Only the file is deleted. The ``ImageMetadata`` row (and everything that
references it -- the analysis, its visual observations) is kept, with
``storage_path`` set to ``NULL``, exactly the same state a ``none``
retention-mode upload already has. Analysis history therefore survives
cleanup; only the raw image bytes are reclaimed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.image import ImageMetadata

logger = logging.getLogger(__name__)


async def cleanup_expired_images(db: AsyncSession, settings: Settings) -> int:
    """Delete on-disk bytes for every image older than the configured TTL.

    Returns the number of images cleaned up. Never raises for a single
    row's failure (a file already missing on disk, a permission error) --
    that row is logged and skipped so one bad row can't block the rest of
    the sweep; only a database error propagates.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.image_retention_ttl_hours)

    result = await db.execute(
        select(ImageMetadata).where(
            ImageMetadata.storage_path.is_not(None),
            ImageMetadata.created_at < cutoff,
        )
    )
    expired = result.scalars().all()

    cleaned = 0
    for image_row in expired:
        path = Path(image_row.storage_path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception(
                "image_cleanup_delete_failed image_id=%s", image_row.id
            )
            continue
        image_row.storage_path = None
        cleaned += 1

    if cleaned:
        await db.commit()
        logger.info("image_cleanup_swept count=%d cutoff=%s", cleaned, cutoff.isoformat())
    return cleaned
