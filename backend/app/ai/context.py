from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import AgentContext
from app.models.memory import Memory
from app.models.project import Goal
from app.models.user import User

# Page-scoped context recipes (design2.md §53). Each entry lists the extra
# blocks to load on top of the always-present `user` block, so the Copilot
# knows what the user is looking at without them repeating it.
#
# Journals are the only user-authored input, so "what I've been doing" is
# always answered from journals and the memories distilled from them.
PAGE_CONTEXT: dict[str, tuple[str, ...]] = {
    "dashboard": ("memories", "recent_journals", "goals"),
    "goal": ("goal", "metrics", "recent_journals", "memories"),
    "goals": ("goals", "recent_journals"),
    "journal": ("recent_journals", "memories"),
    "journals": ("recent_journals",),
    "memory": ("memories", "recent_journals"),
    "memories": ("memories", "recent_journals"),
    "insight": ("insights", "recent_journals"),
    "insights": ("insights",),
}

_LIMIT = 10


class ContextRuntime:
    """Build the compact, user-scoped projection consumed by agents.

    The projection is *page-aware*: a goal page carries the goal plus its
    metrics, journals and memories, a memory page carries memories and the
    journals behind them, and so on. Everything is scoped by ``user_id`` and
    failures degrade to a partial context rather than failing the whole run.
    """

    async def build(self, session: AsyncSession, context: AgentContext) -> dict[str, Any]:
        user = await session.get(User, context.user_id)
        payload: dict[str, Any] = {
            "user": self._user_block(user),
            "page": context.current_page,
        }

        page = (context.current_page or "dashboard").lower()
        object_id = context.current_object_id
        wanted = PAGE_CONTEXT.get(page)

        if wanted is None:
            # Unknown page: fall back to a broad snapshot so the Copilot still
            # has something to reason about.
            wanted = ("goals", "memories", "recent_journals")

        if "goal" in wanted:
            payload["goal"] = await self._goal_block(session, context.user_id, object_id)
        if "goals" in wanted:
            payload["goals"] = await self._goals(session, context.user_id)
        if "metrics" in wanted:
            payload["metrics"] = await self._metrics(session, context.user_id, object_id)
        if "memories" in wanted:
            payload["memories"] = await self._memories(session, context.user_id)
        if "recent_journals" in wanted:
            payload["recent_journals"] = await self._recent_journals(session, context.user_id)
        if "insights" in wanted:
            payload["insights"] = await self._insights(session, context.user_id)

        return payload

    # ------------------------------------------------------------------ blocks

    @staticmethod
    def _user_block(user: User | None) -> dict[str, Any] | None:
        if user is None:
            return None
        return {"id": user.id, "name": user.name, "timezone": user.timezone, "locale": user.locale}

    async def _goal_block(
        self, session: AsyncSession, user_id: str, goal_id: str | None
    ) -> dict[str, Any] | None:
        if not goal_id:
            return None
        goal = await session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            return None
        return {
            "id": goal.id,
            "title": goal.title,
            "description": goal.description,
            "why": goal.why,
            "status": goal.status,
            "priority": goal.priority,
            "progress": float(goal.progress or 0),
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
        }

    async def _goals(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        rows = list(
            (await session.scalars(select(Goal).where(Goal.user_id == user_id).limit(_LIMIT))).unique()
        )
        return [
            {"id": goal.id, "title": goal.title, "status": goal.status, "progress": float(goal.progress or 0)}
            for goal in rows
        ]

    async def _metrics(self, session: AsyncSession, user_id: str, goal_id: str | None) -> list[dict[str, Any]]:
        if not goal_id:
            return []
        goal = await session.get(Goal, goal_id)
        if goal is None or goal.user_id != user_id:
            return []
        from app.models.project import GoalMetric

        rows = list(
            (
                await session.scalars(
                    select(GoalMetric).where(GoalMetric.goal_id == goal_id).limit(20)
                )
            ).unique()
        )
        return [
            {
                "id": metric.id,
                "name": metric.name,
                "metric_type": metric.metric_type,
                "current_value": metric.current_value,
                "target_value": metric.target_value,
                "unit": metric.unit,
            }
            for metric in rows
        ]

    async def _memories(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        rows = list(
            (
                await session.scalars(
                    select(Memory)
                    .where(Memory.user_id == user_id)
                    .order_by(Memory.importance.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {
                "id": memory.id,
                "content": memory.content,
                "type": memory.type,
                "importance": float(memory.importance or 0),
            }
            for memory in rows
        ]

    async def _recent_journals(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        from app.models.journal import Journal

        rows = list(
            (
                await session.scalars(
                    select(Journal)
                    .where(Journal.user_id == user_id)
                    .order_by(Journal.created_at.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {"id": journal.id, "title": journal.title, "content": (journal.content or "")[:500]}
            for journal in rows
        ]

    async def _insights(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        from app.models.insight import Insight

        rows = list(
            (
                await session.scalars(
                    select(Insight)
                    .where(Insight.user_id == user_id)
                    .order_by(Insight.discovered_at.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {
                "id": insight.id,
                "title": insight.title,
                "content": insight.content,
                "insight_type": insight.insight_type,
            }
            for insight in rows
        ]


__all__ = ["ContextRuntime", "PAGE_CONTEXT"]
