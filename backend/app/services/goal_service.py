from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.bus.event_bus import EventBus
from app.models.project import Goal, GoalMetric
from app.repositories.goal_repository import GoalRepository
from app.schemas.common import GoalCreate, GoalUpdate, MetricCreate


class GoalService:
    def __init__(self, repository: GoalRepository, bus: EventBus | None = None):
        self.repository = repository
        self.bus = bus

    async def create(self, session: AsyncSession, user_id: str, data: GoalCreate) -> Goal:
        goal = Goal(
            user_id=user_id,
            title=data.title,
            description=data.description,
            why=data.why,
            priority=data.priority,
            start_date=data.start_date,
            target_date=data.target_date,
        )
        goal = await self.repository.create(session, goal)
        await session.flush()
        if self.bus is not None:
            await self.bus.publish("GoalCreated", {"goal_id": goal.id, "user_id": user_id})
        return goal

    async def get(self, session: AsyncSession, user_id: str, goal_id: str) -> Goal | None:
        return await self.repository.get(session, user_id, goal_id)

    async def list(
        self, session: AsyncSession, user_id: str, status: str | None = None
    ) -> list[Goal]:
        return await self.repository.list(session, user_id, status)

    async def update(
        self, session: AsyncSession, user_id: str, goal_id: str, data: GoalUpdate
    ) -> Goal | None:
        goal = await self.repository.get(session, user_id, goal_id)
        if goal is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        goal = await self.repository.update(session, goal, **fields)
        if self.bus is not None:
            await self.bus.publish(
                "GoalUpdated",
                {"goal_id": goal.id, "user_id": user_id},
            )
        return goal

    async def delete(self, session: AsyncSession, user_id: str, goal_id: str) -> bool:
        return await self.repository.delete(session, user_id, goal_id)

    async def add_metric(
        self, session: AsyncSession, user_id: str, goal_id: str, data: MetricCreate
    ) -> GoalMetric | None:
        goal = await self.repository.get(session, user_id, goal_id)
        if goal is None:
            return None
        metric = GoalMetric(
            goal_id=goal_id,
            name=data.name,
            metric_type=data.metric_type,
            current_value=data.current_value,
            target_value=data.target_value,
            unit=data.unit,
            weight=data.weight,
        )
        return await self.repository.add_metric(session, metric)

    async def recalculate_progress(
        self, session: AsyncSession, user_id: str, goal_id: str
    ) -> float | None:
        """Compute goal progress from linked metric target attainment.

        Weighted average over metrics (weight > 0) clamped to [0, 100].
        """
        goal = await self.repository.get(session, user_id, goal_id)
        if goal is None:
            return None
        metrics = await self.repository.list_metrics(session, goal_id)
        if not metrics:
            return None
        weighted_sum = 0.0
        total_weight = 0.0
        for m in metrics:
            if m.weight <= 0 or m.target_value is None or m.target_value == 0:
                continue
            total_weight += m.weight
            ratio = min(max((m.current_value or 0) / m.target_value, 0.0), 1.0)
            weighted_sum += m.weight * ratio
        if total_weight <= 0:
            return None
        progress = round(weighted_sum / total_weight * 100, 2)
        await self.repository.update(session, goal, progress=progress)
        return progress
