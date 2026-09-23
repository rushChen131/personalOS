from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Goal, GoalMetric


class GoalRepository:
    async def create(self, session: AsyncSession, goal: Goal) -> Goal:
        session.add(goal)
        await session.flush()
        return goal

    async def get(self, session: AsyncSession, user_id: str, goal_id: str) -> Goal | None:
        stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        return await session.scalar(stmt)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Goal]:
        stmt = select(Goal).where(Goal.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Goal.status == status)
        stmt = stmt.order_by(Goal.created_at.desc()).limit(limit).offset(offset)
        return list((await session.scalars(stmt)).unique())

    async def update(self, session: AsyncSession, goal: Goal, **fields) -> Goal:
        for k, v in fields.items():
            setattr(goal, k, v)
        await session.flush()
        return goal

    async def delete(self, session: AsyncSession, user_id: str, goal_id: str) -> bool:
        result = await session.execute(
            delete(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        )
        return result.rowcount > 0

    async def add_metric(self, session: AsyncSession, metric: GoalMetric) -> GoalMetric:
        session.add(metric)
        await session.flush()
        return metric

    async def list_metrics(
        self, session: AsyncSession, goal_id: str
    ) -> list[GoalMetric]:
        stmt = (
            select(GoalMetric)
            .where(GoalMetric.goal_id == goal_id)
            .order_by(GoalMetric.created_at)
        )
        return list((await session.scalars(stmt)).unique())
