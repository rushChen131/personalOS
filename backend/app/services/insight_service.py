from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.bus.event_bus import EventBus
from app.models.base import InsightType
from app.models.insight import Insight
from app.repositories.insight_report_repository import InsightRepository


class InsightService:
    def __init__(self, repository: InsightRepository, bus: EventBus | None = None):
        self.repository = repository
        self.bus = bus

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        title: str,
        content: str,
        insight_type: str = InsightType.PATTERN.value,
        confidence: float = 0.5,
        importance: float = 0.5,
        evidence: list[Any] | None = None,
    ) -> Insight:
        insight = Insight(
            user_id=user_id,
            title=title,
            content=content,
            insight_type=insight_type,
            confidence=confidence,
            importance=importance,
            evidence=evidence or [],
        )
        insight = await self.repository.create(session, insight)
        if self.bus is not None:
            # §80: InsightCreated is part of the public event vocabulary.
            await self.bus.publish("InsightCreated", {"insight_id": insight.id, "user_id": user_id})
        return insight

    async def get(self, session: AsyncSession, user_id: str, insight_id: str) -> Insight | None:
        return await self.repository.get(session, user_id, insight_id)

    async def list(
        self, session: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Insight]:
        return await self.repository.list(session, user_id, limit, offset)
