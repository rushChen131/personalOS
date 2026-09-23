from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import Journal
from app.models.memory import Memory, MemorySource
from app.models.project import Goal
from app.repositories.goal_repository import GoalRepository
from app.schemas.common import ContextResponse
from app.services.goal_service import GoalService


class ContextService:
    """Build page/object-scoped context so the AI Copilot knows what the
    user is looking at without them repeating themselves.

    Projection is journal-centric: journals are the only user-authored input,
    so "what was I doing" is answered from recent journal entries and the
    memories distilled from them, never from raw events.
    """

    def __init__(self) -> None:
        self.goal_service = GoalService(GoalRepository())

    async def build(
        self,
        session: AsyncSession,
        user_id: str,
        page: str,
        object_type: str | None = None,
        object_id: str | None = None,
    ) -> ContextResponse:
        related_journals: list[Journal] = []
        related_memories: list[Memory] = []

        if object_type == "journal" and object_id:
            journal = await session.get(Journal, object_id)
            if journal is not None and journal.user_id == user_id:
                related_journals = [journal]
                mem_stmt = (
                    select(Memory)
                    .join(MemorySource, Memory.id == MemorySource.memory_id)
                    .where(
                        Memory.user_id == user_id,
                        MemorySource.source_type == "JOURNAL",
                        MemorySource.source_id == str(journal.id),
                    )
                    .order_by(Memory.importance.desc())
                    .limit(20)
                )
                related_memories = list((await session.scalars(mem_stmt)).unique())

        elif object_type == "goal" and object_id:
            goal = await session.get(Goal, object_id)
            if goal is not None and goal.user_id == user_id:
                # Memories are the durable signal about a goal's theme; journals
                # supply the recent narrative around it.
                related_memories = list(
                    (
                        await session.scalars(
                            select(Memory)
                            .where(Memory.user_id == user_id)
                            .order_by(Memory.importance.desc())
                            .limit(20)
                        )
                    ).unique()
                )

        if not related_journals:
            stmt = (
                select(Journal)
                .where(Journal.user_id == user_id)
                .order_by(Journal.created_at.desc())
                .limit(10)
            )
            recent_journals = list((await session.scalars(stmt)).unique())
            if object_type == "journal":
                related_journals = recent_journals
            elif not related_memories:
                related_journals = recent_journals

        if not related_journals and not related_memories:
            stmt = (
                select(Memory)
                .where(Memory.user_id == user_id)
                .order_by(Memory.importance.desc())
                .limit(20)
            )
            related_memories = list((await session.scalars(stmt)).unique())

        return ContextResponse(
            page=page,
            object={"type": object_type, "id": object_id},
            related_journals=related_journals,
            related_memories=related_memories,
        )
