from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.journal import Journal
from app.models.memory import MemorySource


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
        category: str | None = None,
    ) -> list[Journal]:
        stmt = select(Journal).where(Journal.user_id == user_id)
        if category:
            stmt = stmt.where(Journal.category == category)
        stmt = stmt.order_by(Journal.created_at.desc()).limit(limit).offset(offset)
        return list((await session.scalars(stmt)).unique())

    async def delete(self, session: AsyncSession, user_id: str, journal_id: str) -> bool:
        journal = await self.get(session, user_id, journal_id)
        if journal is None:
            return False

        # Cut the evidence edge by hand. ``MemorySource.source_id`` is a plain
        # String -- the reference is polymorphic (``source_type`` + ``source_id``)
        # -- so there is no ForeignKey and therefore no cascade to lean on. Left
        # alone, the rows survive pointing at a journal that no longer exists,
        # and the memory they belong to keeps advertising a ``source_count`` it
        # can no longer substantiate. The memory itself is *not* touched: it was
        # promoted on its own merit, and losing one piece of evidence should not
        # silently delete it.
        #
        # ``"JOURNAL"`` is the literal ``MemoryEngine`` writes -- not
        # ``"journal"``. Both id shapes are matched because ``journals.id``
        # stores 32-char dashless hex while ``source_id`` holds the dashed
        # ``str(uuid)``: comparing only one form would silently match nothing.
        await session.execute(
            delete(MemorySource).where(
                MemorySource.source_type == "JOURNAL",
                MemorySource.source_id.in_(
                    {str(journal_id), str(journal_id).replace("-", "")}
                ),
            )
        )

        await session.delete(journal)
        # ``session.delete()`` only *marks* the row; the DELETE statement is not
        # emitted until the session flushes, which -- via ``get_db``'s
        # ``commit()`` after ``yield`` -- happens after the response has already
        # been sent. A client that reads immediately (exactly what a UI does
        # after deleting) could therefore still see the row. Flushing here emits
        # the DELETE while the request is still open.
        # ``TodoRepository.delete`` never showed the symptom because it uses a
        # bulk ``delete()`` statement, which executes straight away.
        #
        # Note this narrows the window rather than eliminating it: durability
        # still depends on the commit in ``get_db``, which only lands after the
        # response. It is not reproducible in-process -- ``TestClient`` runs the
        # dependency teardown before returning -- so verifying it needs a real
        # server (see ``scripts/live_check.py``).
        await session.flush()
        return True
