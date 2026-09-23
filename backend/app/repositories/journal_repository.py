from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import Journal


class JournalRepository:
    async def create(self, session: AsyncSession, journal: Journal) -> Journal:
        session.add(journal)
        await session.flush()
        return journal

    async def get(self, session: AsyncSession, user_id: str, journal_id: str) -> Journal | None:
        stmt = select(Journal).where(Journal.id == journal_id, Journal.user_id == user_id)
        return await session.scalar(stmt)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Journal]:
        stmt = (
            select(Journal)
            .where(Journal.user_id == user_id)
            .order_by(Journal.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())

    async def delete(self, session: AsyncSession, user_id: str, journal_id: str) -> bool:
        journal = await self.get(session, user_id, journal_id)
        if journal is None:
            return False
        await session.delete(journal)
        return True
