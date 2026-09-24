from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report import Report


class ReportRepository:
    """Query-level access to the ``reports`` table.

    One report is identified by ``(user_id, type, period_start, period_end,
    dimension)`` — the engine relies on that tuple to refresh in place instead
    of stacking duplicates.
    """

    async def create(self, session: AsyncSession, report: Report) -> Report:
        session.add(report)
        await session.flush()
        return report

    async def get(self, session: AsyncSession, user_id: str, report_id: str) -> Report | None:
        stmt = select(Report).where(Report.id == report_id, Report.user_id == user_id)
        return await session.scalar(stmt)

    async def find(
        self,
        session: AsyncSession,
        user_id: str,
        report_type: str,
        period_start: date,
        period_end: date,
        dimension: str,
    ) -> Report | None:
        stmt = select(Report).where(
            Report.user_id == user_id,
            Report.type == report_type,
            Report.period_start == period_start,
            Report.period_end == period_end,
            Report.dimension == dimension,
        )
        return await session.scalar(stmt)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        report_type: str | None = None,
        dimension: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Report]:
        stmt = select(Report).where(Report.user_id == user_id)
        if report_type:
            stmt = stmt.where(Report.type == report_type)
        if dimension:
            stmt = stmt.where(Report.dimension == dimension)
        # Newest period first; type breaks ties so a daily and a monthly
        # covering the same day have a stable order.
        stmt = (
            stmt.order_by(Report.period_end.desc(), Report.period_start.desc(), Report.type.asc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())

    async def delete(self, session: AsyncSession, user_id: str, report_id: str) -> bool:
        report = await self.get(session, user_id, report_id)
        if report is None:
            return False
        await session.delete(report)
        return True
