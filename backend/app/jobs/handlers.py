from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import CandidateStatus
from app.models.memory import Memory, MemoryCandidate, MemorySource


class MemoryAnalysisJob:
    """Feed a created journal entry into the §83 candidate pipeline.

    Journals never become Memory directly — the MemoryEngine splits the entry
    into cognitive statements, folds them into evidence buckets, and promotes
    a bucket to Memory only once thresholds are met.
    """

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.models.journal import Journal
        from app.services.memory_engine import MemoryEngine

        journal_id = payload.get("journal_id")
        if not journal_id:
            return {"skipped": "no journal_id"}
        journal = await session.scalar(
            select(Journal).where(Journal.id == journal_id, Journal.user_id == user_id)
        )
        if journal is None or not journal.content:
            return {"skipped": "journal not found"}

        return await MemoryEngine().ingest_journal(session, user_id, journal)


class EmbeddingJob:
    """Compute and persist the embedding for a newly created journal entry.

    Journals are the entry point of the pipeline, so their vectors are what
    semantic search ranks. The vector is stored on any Memory distilled from
    the journal, and on the Journal row itself. A deterministic local embedder
    keeps this working without any API key.
    """

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.ai.gateway.embeddings import build_embedding_provider
        from app.models.journal import Journal

        journal_id = payload.get("journal_id")
        if not journal_id:
            return {"skipped": "no journal_id"}

        journal = await session.scalar(
            select(Journal).where(Journal.id == journal_id, Journal.user_id == user_id)
        )
        if journal is None or not journal.content:
            return {"skipped": "journal not found"}

        provider = build_embedding_provider()
        text = f"{journal.title or ''} {journal.content}".strip()
        vector = (await provider.embed([text]))[0]

        # Attach the vector to any memory that references this journal, so
        # semantic search can rank them; skip cleanly when none exist yet.
        memories = list(
            (
                await session.scalars(
                    select(Memory)
                    .join(MemorySource, Memory.id == MemorySource.memory_id)
                    .where(
                        Memory.user_id == user_id,
                        MemorySource.source_type == "JOURNAL",
                        MemorySource.source_id == str(journal_id),
                    )
                )
            ).unique()
        )
        for memory in memories:
            if memory.embedding is None:
                memory.embedding = vector
        await session.flush()
        return {
            "status": "embedded",
            "provider": provider.provider,
            "dim": len(vector),
            "memories_updated": len(memories),
        }


class MemoryCompactionJob:
    """Flag stale, low-importance memories for review, and prune dead
    memory candidates (§83) so the staging table cannot grow without bound.

    Memory pruning stays non-destructive (it only reports ids). Candidate
    pruning is destructive by design, but only removes rows that will never
    promote: REJECTED buckets, or PENDING buckets that have seen no new
    evidence for a long window.
    """

    #: A pending candidate with no fresh evidence for this long is dead weight.
    CANDIDATE_TTL_DAYS = 180

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Must be timezone-aware: it is compared against updated_at and
        # last_seen_at, which are stored as UTC.
        cutoff = datetime.now(timezone.utc)
        rows = list(
            (
                await session.scalars(
                    select(Memory).where(Memory.user_id == user_id, Memory.importance < 0.3).limit(200)
                )
            ).unique()
        )
        stale = [m.id for m in rows if m.updated_at and (cutoff - m.updated_at).days > 90]

        # -- candidate pruning (bounds memory_candidates growth) ----------
        candidate_cutoff = cutoff - timedelta(days=self.CANDIDATE_TTL_DAYS)
        dead = list(
            (
                await session.scalars(
                    select(MemoryCandidate).where(
                        MemoryCandidate.user_id == user_id,
                        MemoryCandidate.status != CandidateStatus.PROMOTED.value,
                        MemoryCandidate.last_seen_at.is_not(None),
                        MemoryCandidate.last_seen_at < candidate_cutoff,
                    )
                )
            ).unique()
        )
        for candidate in dead:
            await session.delete(candidate)
        if dead:
            await session.flush()

        return {
            "candidates": len(stale),
            "ids": stale,
            "pruned_candidates": len(dead),
            "as_of": cutoff.isoformat(),
        }


class ReportGenerationJob:
    """Build one period report from the journals already on file.

    Always targets the period that has just **finished**, so a report never
    summarises a day still in progress — which is what makes a 00:05 cron
    correct. Weekly and monthly generation honour the matching ``UserSetting``
    toggle; the daily report has no toggle.
    """

    #: report type -> the ``UserSetting`` flag that gates it.
    SETTING_FLAGS = {
        "WEEKLY": "weekly_report_enabled",
        "MONTHLY": "monthly_report_enabled",
    }

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.models.user import UserSetting
        from app.services.report_engine import (
            SUPPORTED_TYPES,
            ReportEngine,
            previous_period_bounds,
        )

        report_type = (payload.get("report_type") or "DAILY").upper()
        if report_type not in SUPPORTED_TYPES:
            return {"skipped": f"unsupported report_type: {report_type}"}

        flag = self.SETTING_FLAGS.get(report_type)
        if flag:
            enabled = await session.scalar(
                select(getattr(UserSetting, flag)).where(UserSetting.user_id == user_id)
            )
            # A user with no settings row yet keeps the column default (enabled).
            if enabled is False:
                return {"skipped": f"{flag} disabled"}

        start, end = previous_period_bounds(report_type, datetime.now(timezone.utc).date())
        report = await ReportEngine().generate(
            session, user_id, report_type, period_start=start, period_end=end
        )
        return {
            "report_id": report.id,
            "type": report.type,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "journal_count": (report.content or {}).get("journal_count", 0),
        }
