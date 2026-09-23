from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.bus.event_bus import EventBus
from app.models.base import EventSource
from app.models.journal import Journal
from app.repositories.journal_repository import JournalRepository
from app.schemas.common import JournalCreate


class JournalService:
    def __init__(self, repository: JournalRepository, bus: EventBus):
        self.repository = repository
        self.bus = bus

    async def create(self, session: AsyncSession, user_id: str, data: JournalCreate) -> Journal:
        journal = Journal(
            user_id=user_id,
            title=data.title,
            content=data.content,
            source=EventSource(data.source).value if data.source else EventSource.MANUAL.value,
            mood=data.mood,
            metadata=data.metadata,
            occurred_at=data.occurred_at,
        )
        journal = await self.repository.create(session, journal)
        await self.bus.publish(
            "JournalCreated",
            {"journal_id": journal.id, "user_id": user_id},
        )
        return journal

    async def get(self, session: AsyncSession, user_id: str, journal_id: str) -> Journal | None:
        return await self.repository.get(session, user_id, journal_id)

    async def list(
        self, session: AsyncSession, user_id: str, limit: int = 100, offset: int = 0
    ) -> list[Journal]:
        return await self.repository.list(session, user_id, limit, offset)

    async def delete(self, session: AsyncSession, user_id: str, journal_id: str) -> bool:
        return await self.repository.delete(session, user_id, journal_id)
