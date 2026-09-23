"""Entry point for the containerised job worker.

Usage: ``python -m app.jobs.worker``

Runs the arq worker when Redis is configured (RedisEventBus / arq path).
Falls back to a simple polling loop over the in-process dispatcher when Redis
is unavailable, so the same command works in local and production shapes.
"""

from __future__ import annotations

import asyncio


async def main() -> None:
    from app.core.config import settings
    from app.core.logging import logger

    if settings.is_sqlite:
        logger.warning("worker.in_process_mode", reason="sqlite database configured; arq requires Redis+PG")
        await _fallback_loop()
        return

    try:
        from arq import run_worker

        from app.jobs.worker import WorkerSettings

        logger.info("worker.arq.start", redis=settings.redis_url)
        await run_worker(WorkerSettings)
    except Exception as exc:  # noqa: BLE001 - arq/redis optional
        logger.error("worker.arq.failed", error=str(exc))
        await _fallback_loop()


async def _fallback_loop() -> None:
    """Run scheduled jobs on a fixed interval without Redis."""
    from app.core.logging import logger
    from app.jobs.in_process import dispatcher

    await dispatcher.register()
    interval = 3600
    logger.info("worker.fallback.start", interval_seconds=interval)
    while True:
        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
