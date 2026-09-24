"""Deterministic period reports (daily / weekly / monthly).

The engine is **pure aggregation over journals** — the only user-authored
input — with a fixed ``content`` contract. It deliberately does not call an
LLM: reports must be reproducible and must work with no API key configured.
When a natural-language narrative is wanted, the AI copilot reads ``content``
through the ``query_reports`` tool and phrases it on demand, which also avoids
persisting prose that goes stale.

Nothing here writes to ``journals`` / ``todos`` / ``memories``; the engine only
reads them and writes one row to the pre-existing ``reports`` table, so the
task produces **no schema change**.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Category, ReportType
from app.models.journal import Journal
from app.models.memory import Memory
from app.models.project import Todo
from app.models.report import Report
from app.models.user import User
from app.repositories.report_repository import ReportRepository

#: How many journal excerpts a report carries.
HIGHLIGHT_LIMIT = 5
#: Characters kept from each highlighted journal.
EXCERPT_CHARS = 160
#: Life domain covering every category at once.
DIMENSION_ALL = "ALL"

SUPPORTED_TYPES: tuple[str, ...] = (
    ReportType.DAILY.value,
    ReportType.WEEKLY.value,
    ReportType.MONTHLY.value,
)

#: Concurrent generations for one user must not both insert, so the
#: find-or-create step is serialised per user. The registry is module-level on
#: purpose: a fresh engine is built for every request and every job, so an
#: instance-level lock would never be shared.
_LOCKS: dict[str, asyncio.Lock] = {}


def _lock_for(user_id: str) -> asyncio.Lock:
    return _LOCKS.setdefault(user_id, asyncio.Lock())


def period_bounds(report_type: str, reference: date) -> tuple[date, date]:
    """Inclusive ``(start, end)`` of the period containing ``reference``.

    Weeks follow ISO: Monday through Sunday.
    """
    if report_type == ReportType.DAILY.value:
        return reference, reference
    if report_type == ReportType.WEEKLY.value:
        start = reference - timedelta(days=reference.weekday())
        return start, start + timedelta(days=6)
    if report_type == ReportType.MONTHLY.value:
        start = reference.replace(day=1)
        # Day 1 of the following month, minus one day, is the last day of this
        # one — handles 28/29/30/31 without a calendar table.
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)
    raise ValueError(f"unsupported report type: {report_type}")


def previous_period_bounds(report_type: str, reference: date) -> tuple[date, date]:
    """Inclusive bounds of the period *before* the one containing ``reference``.

    Stepping one day back from the current period's start lands inside the
    previous period, whatever its length.
    """
    start, _ = period_bounds(report_type, reference)
    return period_bounds(report_type, start - timedelta(days=1))


def normalise_dimension(dimension: str | None) -> str:
    """Map a requested dimension onto ``ALL`` or a known ``Category``.

    Unknown values collapse to ``ALL`` so a stale client cannot silently
    produce an empty report.
    """
    if not dimension or dimension.upper() == DIMENSION_ALL:
        return DIMENSION_ALL
    try:
        return Category(dimension.upper()).value
    except ValueError:
        return DIMENSION_ALL


def _normalise_locale(value: str | None) -> str:
    return "en" if (value or "").lower().startswith("en") else "zh"


class ReportEngine:
    """Aggregate a period of journals into one ``Report`` row."""

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.reports = repository or ReportRepository()

    async def generate(
        self,
        session: AsyncSession,
        user_id: str,
        report_type: str,
        period_start: date | None = None,
        period_end: date | None = None,
        dimension: str | None = None,
    ) -> Report:
        """Build (or refresh) the report for a period.

        Calling twice with the same arguments refreshes the existing row rather
        than inserting a duplicate.
        """
        if report_type not in SUPPORTED_TYPES:
            raise ValueError(f"unsupported report type: {report_type}")
        resolved_dimension = normalise_dimension(dimension)

        if period_start is None or period_end is None:
            # UTC is the only calendar available (no tzdata on this platform),
            # so callers that know the user's real local date — the frontend and
            # the cron jobs — pass explicit bounds.
            start, end = period_bounds(report_type, datetime.now(timezone.utc).date())
        else:
            start, end = period_start, period_end
        if end < start:
            start, end = end, start

        locale = _normalise_locale(await self._user_locale(session, user_id))

        async with _lock_for(user_id):
            content = await self._aggregate(session, user_id, start, end, resolved_dimension)
            title = self._title(report_type, start, end, locale)
            summary = self._render_summary(report_type, start, end, content, locale)

            existing = await self.reports.find(
                session, user_id, report_type, start, end, resolved_dimension
            )
            if existing is not None:
                existing.title = title
                existing.summary = summary
                existing.content = content
                existing.status = "COMPLETED"
                await session.flush()
                return existing

            report = Report(
                user_id=user_id,
                definition_id=None,
                type=report_type,
                dimension=resolved_dimension,
                period_start=start,
                period_end=end,
                title=title,
                summary=summary,
                content=content,
                status="COMPLETED",
            )
            return await self.reports.create(session, report)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        report_type: str | None = None,
        dimension: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Report]:
        return await self.reports.list(session, user_id, report_type, dimension, limit, offset)

    async def get(self, session: AsyncSession, user_id: str, report_id: str) -> Report | None:
        return await self.reports.get(session, user_id, report_id)

    async def delete(self, session: AsyncSession, user_id: str, report_id: str) -> bool:
        return await self.reports.delete(session, user_id, report_id)

    async def _user_locale(self, session: AsyncSession, user_id: str) -> str | None:
        return await session.scalar(select(User.locale).where(User.id == user_id))

    async def _aggregate(
        self,
        session: AsyncSession,
        user_id: str,
        start: date,
        end: date,
        dimension: str,
    ) -> dict[str, Any]:
        """Collect the fixed ``content`` contract for ``[start, end]``."""
        start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
        # Exclusive upper bound, so an entry logged late on ``end`` is included
        # exactly once.
        end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)

        stmt = select(Journal).where(
            Journal.user_id == user_id,
            Journal.created_at >= start_dt,
            Journal.created_at < end_dt,
        )
        if dimension != DIMENSION_ALL:
            stmt = stmt.where(Journal.category == dimension)
        journals = list((await session.scalars(stmt)).unique())

        category_counts = Counter(journal.category or Category.OTHER.value for journal in journals)
        mood_counts = Counter(journal.mood for journal in journals if journal.mood)
        active_days = len(
            {(journal.created_at.date() if journal.created_at else start) for journal in journals}
        )

        corpus = "\n".join((journal.content or "") for journal in journals).lower()
        todos = list(await session.scalars(select(Todo).where(Todo.user_id == user_id)))
        touched_todos = [
            todo
            for todo in todos
            if (todo.title or "").strip()
            and (todo.title or "").strip().lower() in corpus
            and (dimension == DIMENSION_ALL or (todo.category or Category.OTHER.value) == dimension)
        ]

        memory_stmt = select(Memory).where(
            Memory.user_id == user_id,
            Memory.created_at >= start_dt,
            Memory.created_at < end_dt,
        )
        if dimension != DIMENSION_ALL:
            memory_stmt = memory_stmt.where(Memory.category == dimension)
        memories = list((await session.scalars(memory_stmt)).unique())

        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": (end - start).days + 1,
            },
            "journal_count": len(journals),
            "active_days": active_days,
            "category_breakdown": self._ordered_counts(category_counts),
            "mood_breakdown": self._ordered_counts(mood_counts),
            "todos": [
                {
                    "id": todo.id,
                    "title": todo.title,
                    "category": todo.category,
                    "completed": todo.completed_at is not None,
                    "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
                }
                for todo in sorted(touched_todos, key=lambda item: item.title or "")
            ],
            "memories": [
                {"id": memory.id, "content": memory.content, "category": memory.category}
                for memory in sorted(memories, key=lambda item: item.id)
            ],
            "highlights": self._highlights(journals),
        }

    @staticmethod
    def _ordered_counts(counter: Counter[str]) -> dict[str, int]:
        """Counts ordered by size, then key — a stable shape for assertions."""
        return {key: count for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))}

    @staticmethod
    def _highlights(journals: list[Journal]) -> list[dict[str, Any]]:
        """The most substantial entries of the period, deterministically ranked."""
        ranked = sorted(
            journals,
            key=lambda journal: (
                -len(journal.content or ""),
                -(journal.created_at.timestamp() if journal.created_at else 0.0),
            ),
        )
        highlights: list[dict[str, Any]] = []
        for journal in ranked[:HIGHLIGHT_LIMIT]:
            text = (journal.content or "").strip().replace("\n", " ")
            highlights.append(
                {
                    "journal_id": journal.id,
                    "title": journal.title,
                    "excerpt": text[:EXCERPT_CHARS],
                    "occurred_at": journal.created_at.isoformat() if journal.created_at else None,
                }
            )
        return highlights

    @staticmethod
    def _title(report_type: str, start: date, end: date, locale: str) -> str:
        """Stable, count-free title — the de-duplication key depends on it."""
        if report_type == ReportType.DAILY.value:
            period = start.isoformat()
        elif report_type == ReportType.MONTHLY.value:
            period = f"{start.year:04d}-{start.month:02d}"
        else:
            period = f"{start.isoformat()} ~ {end.isoformat()}"
        if locale == "en":
            label = {
                ReportType.DAILY.value: "Daily Report",
                ReportType.WEEKLY.value: "Weekly Report",
                ReportType.MONTHLY.value: "Monthly Report",
            }[report_type]
        else:
            label = {
                ReportType.DAILY.value: "日报",
                ReportType.WEEKLY.value: "周报",
                ReportType.MONTHLY.value: "月报",
            }[report_type]
        return f"{period} {label}"

    @staticmethod
    def _render_summary(
        report_type: str,
        start: date,
        end: date,
        content: dict[str, Any],
        locale: str,
    ) -> str:
        """Template-rendered narrative. No model call, so it never drifts."""
        count = content["journal_count"]
        active_days = content["active_days"]
        span = f"{start.isoformat()} ~ {end.isoformat()}"
        categories = list(content["category_breakdown"].items())
        moods = list(content["mood_breakdown"].items())
        todos = content["todos"]
        memories = content["memories"]

        if locale == "en":
            if count == 0:
                head = f"No journal entries were recorded for {span}."
            else:
                head = (
                    f"{count} journal {'entry' if count == 1 else 'entries'} recorded "
                    f"over {span}, spread across {active_days} "
                    f"{'day' if active_days == 1 else 'days'}."
                )
            parts = [head]
            if categories:
                top = ", ".join(f"{name} ({n})" for name, n in categories[:3])
                parts.append(f"Most active areas: {top}.")
            if moods:
                parts.append(f"Mood was mostly {moods[0][0]}.")
            if todos:
                titles = ", ".join(f"「{todo['title']}」" for todo in todos[:3])
                parts.append(f"Todos touched: {titles}.")
            if memories:
                noun = "memory" if len(memories) == 1 else "memories"
                parts.append(f"{len(memories)} long-term {noun} distilled this period.")
            return " ".join(parts)

        if count == 0:
            head = f"{span} 期间没有新的日志记录。"
        else:
            head = f"{span} 共记录 {count} 篇日志，覆盖 {active_days} 天。"
        parts = [head]
        if categories:
            top = "、".join(f"{name} {n} 篇" for name, n in categories[:3])
            parts.append(f"主要集中在 {top}。")
        if moods:
            parts.append(f"心情以 {moods[0][0]} 为主。")
        if todos:
            parts.append("涉及待办：" + "、".join(f"「{todo['title']}」" for todo in todos[:3]) + "。")
        if memories:
            parts.append(f"本期沉淀 {len(memories)} 条长期记忆。")
        return "".join(parts)
