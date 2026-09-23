from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory, MemorySource


class MemoryRepository:
    async def create(self, session: AsyncSession, memory: Memory) -> Memory:
        session.add(memory)
        await session.flush()
        return memory

    async def get(self, session: AsyncSession, user_id: str, memory_id: str) -> Memory | None:
        stmt = select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
        return await session.scalar(stmt)

    async def add_source(self, session: AsyncSession, source: MemorySource) -> MemorySource:
        session.add(source)
        await session.flush()
        return source

    async def list_sources(self, session: AsyncSession, memory_id: str) -> list[MemorySource]:
        stmt = (
            select(MemorySource)
            .where(MemorySource.memory_id == memory_id)
            .order_by(MemorySource.created_at)
        )
        return list((await session.scalars(stmt)).unique())

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())

    async def search(
        self,
        session: AsyncSession,
        user_id: str,
        query: str | None = None,
        memory_type: str | None = None,
        importance_min: float | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.user_id == user_id)

        if query:
            like = f"%{query}%"
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    Memory.content.ilike(like),
                    Memory.summary.ilike(like),
                )
            )
        if memory_type:
            stmt = stmt.where(Memory.type == memory_type)
        if importance_min is not None:
            stmt = stmt.where(Memory.importance >= importance_min)
        if from_time is not None:
            stmt = stmt.where(Memory.created_at >= from_time)
        if to_time is not None:
            stmt = stmt.where(Memory.created_at <= to_time)

        stmt = (
            stmt.order_by(Memory.importance.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())
