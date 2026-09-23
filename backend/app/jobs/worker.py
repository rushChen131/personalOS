from __future__ import annotations

from typing import Any

from app.core.logging import logger
from app.jobs.in_process import REGISTRY


async def run_job(ctx: dict[str, Any], job_type: str, user_id: str, payload: dict[str, Any] | None = None) -> dict:
    """arq task entry point; shares the handler registry with in-process mode."""
    from app.core.database import SessionLocal

    handler = REGISTRY.get(job_type)
    if handler is None:
        logger.error("jobs.worker.unknown", job_type=job_type)
        return {"error": f"unknown job_type: {job_type}"}
    async with SessionLocal() as session:
        result = await handler(session, user_id, payload or {})
        await session.commit()
        return result


async def memory_compaction(ctx: dict[str, Any], user_id: str) -> dict:
    return await run_job(ctx, "memory_compaction", user_id, {})


async def startup(ctx: dict[str, Any]) -> None:
    logger.info("jobs.worker.startup")


async def shutdown(ctx: dict[str, Any]) -> None:
    logger.info("jobs.worker.shutdown")


class WorkerSettings:
    """arq worker definition (production).

    Run with: ``arq app.jobs.worker.WorkerSettings``

    Scheduled jobs (design2.md §57):
      - memory_compaction Sunday 05:00

    The report crons were removed along with the Report module; the only
    user-authored input is the journal, whose per-entry fan-out (embedding,
    memory distillation, goal progress) is driven by the
    ``JournalCreated`` event rather than a wall-clock schedule.

    Not scheduled automatically in local mode; use the in-process dispatcher
    (``app.jobs.in_process.dispatcher.run_job``) instead.
    """

    functions = [
        run_job,
        memory_compaction,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None
    cron_jobs: list[Any] = []
    max_jobs = 10
    job_timeout = 300

    @classmethod
    def build(cls) -> type:
        """Attach Redis settings and the cron schedule at import time."""
        from arq import cron
        from arq.connections import RedisSettings

        from app.core.config import settings

        async def with_user(ctx: dict[str, Any], job_name: str, payload: dict[str, Any] | None = None) -> None:
            from sqlalchemy import select

            from app.core.database import SessionLocal
            from app.models.user import User

            async with SessionLocal() as session:
                user_ids = list((await session.scalars(select(User.id))).unique())
            for user_id in user_ids:
                await run_job(ctx, job_name, user_id, payload or {})

        async def cron_memory_compaction(ctx: dict[str, Any]) -> None:
            await with_user(ctx, "memory_compaction")

        cls.redis_settings = RedisSettings.from_dsn(settings.redis_url)
        cls.cron_jobs = [
            # Housekeeping: Sunday 05:00.
            cron(cron_memory_compaction, weekday="sun", hour=5, minute=0),
        ]
        return cls


try:  # pragma: no cover - only meaningful when arq is installed
    WorkerSettings = WorkerSettings.build()
except Exception:  # noqa: BLE001 - arq optional in local mode
    logger.warning("jobs.worker.cron_unavailable", reason="arq not configured")
