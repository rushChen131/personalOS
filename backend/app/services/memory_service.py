from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.bus.event_bus import EventBus
from app.models.memory import Memory
from app.repositories.memory_repository import MemoryRepository
from app.schemas.common import MemorySearchRequest


class MemoryService:
    """Read-only access to promoted memories.

    Memories are never authored directly: they are distilled from journal
    entries by ``MemoryEngine`` (§83). This service therefore exposes only
    read paths — the manual ``create`` route was removed with the memories
    page form so that every Memory stays traceable to its source journals.
    """

    def __init__(self, repository: MemoryRepository, bus: EventBus):
        self.repository = repository
        self.bus = bus

    async def get(self, session: AsyncSession, user_id: str, memory_id: str) -> Memory | None:
        return await self.repository.get(session, user_id, memory_id)

    async def list(
        self, session: AsyncSession, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Memory]:
        return await self.repository.list(session, user_id, limit, offset)

    async def search(
        self, session: AsyncSession, user_id: str, req: MemorySearchRequest
    ) -> list[Memory]:
        return await self.repository.search(
            session,
            user_id,
            query=req.query,
            memory_type=req.memory_type,
            importance_min=req.importance_min,
            from_time=req.from_time,
            to_time=req.to_time,
            limit=req.limit,
            offset=req.offset,
        )
