from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.logging import logger
from app.infrastructure.bus.event_bus import EventBus, event_bus
from app.jobs.handlers import (
    EmbeddingJob,
    GoalProgressJob,
    InsightAnalysisJob,
    MemoryAnalysisJob,
    MemoryCompactionJob,
)

JobCallable = Callable[[AsyncSession, str, dict[str, Any]], Awaitable[dict[str, Any]]]

REGISTRY: dict[str, JobCallable] = {
    "goal_progress": GoalProgressJob().run,
    "memory_analysis": MemoryAnalysisJob().run,
    "insight_analysis": InsightAnalysisJob().run,
    "embedding": EmbeddingJob().run,
    "memory_compaction": MemoryCompactionJob().run,
}


class InProcessDispatcher:
    """Local-mode replacement for an arq worker.

    Wires the JournalCreated fan-out (EmbeddingJob / GoalProgressJob /
    MemoryAnalysisJob / InsightAnalysisJob), so one journal entry drives
    embedding, memory distillation and insight detection. Exposes ``run_job``
    so scheduled jobs can be triggered manually without Redis.

    The bus fires while the publisher's transaction is still open, so handlers
    opening their own session would not see the new row. Follow-up jobs are
    therefore deferred until after the request commits (see ``defer``).

    Deferred jobs are keyed by **event id** rather than appended to a single
    shared list: when many requests run concurrently against the same process
    they drain independently after their own commit, so one request can never
    steal another's pending work.
    """

    def __init__(self, bus: EventBus | None = None, defer_writes: bool = True) -> None:
        self.bus = bus or event_bus
        self._registered = False
        self._after_commit: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
        self._inline = not defer_writes

    async def register(self) -> None:
        if self._registered:
            return
        await self.bus.subscribe("JournalCreated", self._on_journal_created)
        self._registered = True
        logger.info("jobs.in_process.registered")

    def schedule(
        self,
        job_type: str,
        user_id: str,
        payload: dict[str, Any] | None = None,
        *,
        key: str = "__global__",
    ) -> None:
        """Queue a job to run after the current request commits.

        ``key`` scopes the queue (normally the triggering entity id) so that
        concurrent requests drain only their own follow-up work.
        """
        self._after_commit.setdefault(key, []).append((job_type, user_id, payload or {}))

    def drain_scheduled(self, key: str | None = None) -> list[tuple[str, str, dict[str, Any]]]:
        if key is None:
            scheduled = [job for jobs in self._after_commit.values() for job in jobs]
            self._after_commit = {}
            return scheduled
        return self._after_commit.pop(key, [])

    async def _on_journal_created(self, payload: dict[str, Any]) -> None:
        user_id = payload.get("user_id")
        journal_id = payload.get("journal_id")
        if not user_id:
            return
        # A journal entry is the single user-facing input, so it fans out to
        # the whole downstream pipeline: embedding, memory distillation,
        # insight detection, and goal-progress refresh.
        jobs = (
            ("embedding", {"journal_id": journal_id}),
            ("memory_analysis", {"journal_id": journal_id}),
            ("insight_analysis", {"period_days": 14}),
            ("goal_progress", {"journal_id": journal_id}),
        )
        if self._inline:
            for job_type, job_payload in jobs:
                await self.run_job(job_type, user_id, job_payload)
        else:
            for job_type, job_payload in jobs:
                self.schedule(job_type, user_id, job_payload, key=journal_id or "__global__")

    async def run_job(self, job_type: str, user_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = REGISTRY.get(job_type)
        if handler is None:
            return {"error": f"unknown job_type: {job_type}"}
        async with SessionLocal() as session:
            try:
                result = await handler(session, user_id, payload or {})
                await session.commit()
                logger.info("jobs.in_process.completed", job_type=job_type, user_id=user_id)
                return result
            except Exception as exc:
                await session.rollback()
                logger.error("jobs.in_process.failed", job_type=job_type, error=str(exc))
                return {"error": str(exc)}

    async def drain_and_run(self, key: str | None = None) -> None:
        """Execute jobs queued by handlers during the request; call after commit.

        A single failing handler must not prevent the remaining follow-up
        jobs from running, so each job is isolated.
        """
        for job_type, user_id, payload in self.drain_scheduled(key):
            try:
                await self.run_job(job_type, user_id, payload)
            except Exception as exc:  # defensive: run_job already swallows its own errors
                logger.error("jobs.in_process.drain_failed", job_type=job_type, error=str(exc))


dispatcher = InProcessDispatcher()
