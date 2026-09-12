"""Standalone entry point: ``python -m app.jobs.cleanup_images``.

Runs one sweep of ``app.core.image_cleanup.cleanup_expired_images`` and
exits -- suitable for an external cron, a `docker compose exec` call, or
manual invocation. The running API process also runs this on its own
periodic loop (see ``app.main``'s lifespan), so this script is a manual/
external supplement, not the only way the cleanup happens.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.core.image_cleanup import cleanup_expired_images
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run() -> int:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        return await cleanup_expired_images(db, settings)


def main() -> None:
    cleaned = asyncio.run(_run())
    logger.info("cleanup_images_done count=%d", cleaned)
    print(f"Cleaned up {cleaned} expired image(s).")


if __name__ == "__main__":
    main()
