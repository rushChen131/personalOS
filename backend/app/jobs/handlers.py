from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.base import CandidateStatus
from app.models.memory import Memory, MemoryCandidate, MemorySource
from app.models.project import Goal
from app.repositories.insight_report_repository import InsightRepository


class GoalProgressJob:
    """Recompute a goal's progress from how much the user writes about it.

    Journals are the only user-authored signal, so effort is proxied by the
    number of journal entries within the window that mention the goal's theme.
    """

    #: Journal entries referencing a goal that saturate its progress at 100%.
    ENTRIES_FOR_FULL_PROGRESS = 20
    WINDOW_DAYS = 90

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.models.journal import Journal

        goal_id = payload.get("goal_id")
        if not goal_id:
            return {"skipped": "no goal_id"}
        goal = await session.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id))
        if goal is None:
            return {"skipped": "goal not found"}

        since = datetime.now(timezone.utc) - timedelta(days=self.WINDOW_DAYS)
        term = (goal.title or "").strip()
        stmt = select(Journal).where(Journal.user_id == user_id, Journal.created_at >= since)
        if term:
            stmt = stmt.where(Journal.content.ilike(f"%{term}%"))
        entries = list((await session.scalars(stmt)).unique())

        effort = min(1.0, len(entries) / self.ENTRIES_FOR_FULL_PROGRESS)
        confidence = 0.4 + min(0.4, len(entries) * 0.05)
        if goal.target_date:
            logger.info("goal.progress.recompute", goal_id=goal_id, target=str(goal.target_date))

        goal.progress = round(effort * 100, 2)
        goal.metadata_ = {
            **(goal.metadata_ or {}),
            "progress_source": "GOAL_PROGRESS_JOB",
            "confidence": confidence,
        }
        await session.flush()
        return {"goal_id": goal_id, "progress": goal.progress, "journal_entries": len(entries)}


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


class InsightAnalysisJob:
    """Run the rule-based insight engine for the triggering user."""

    async def run(self, session: AsyncSession, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.infrastructure.bus.event_bus import event_bus
        from app.services.insight_engine import InsightEngine

        engine = InsightEngine(InsightRepository(), event_bus)
        insights = await engine.generate(session, user_id, period_days=int(payload.get("period_days", 14)))
        return {"insights_created": len(insights), "ids": [i.id for i in insights]}


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
