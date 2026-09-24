from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Todo, TodoMetric


class TodoRepository:
    async def create(self, session: AsyncSession, todo: Todo) -> Todo:
        session.add(todo)
        await session.flush()
        return todo

    async def get(self, session: AsyncSession, user_id: str, todo_id: str) -> Todo | None:
        stmt = select(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
        return await session.scalar(stmt)

    async def get_with_children(
        self, session: AsyncSession, user_id: str, todo_id: str
    ) -> Todo | None:
        stmt = (
            select(Todo)
            .where(Todo.id == todo_id, Todo.user_id == user_id)
            .options(selectinload(Todo.children))
        )
        return await session.scalar(stmt)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        completed: bool | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Todo]:
        """Every todo in one flat list, parents and steps alike.

        Kept for callers that genuinely want a flat set (reports, the insight
        engine). Anything user-facing wants :meth:`list_tree` instead, so a step
        is never mistaken for a top-level item.
        """
        stmt = select(Todo).where(Todo.user_id == user_id)
        if completed is not None:
            stmt = stmt.where(
                Todo.completed_at.is_(None) if not completed else Todo.completed_at.is_not(None)
            )
        if category:
            stmt = stmt.where(Todo.category == category)
        stmt = (
            stmt.order_by(Todo.completed_at.is_(None).desc(), Todo.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())

    async def list_tree(
        self,
        session: AsyncSession,
        user_id: str,
        completed: bool | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Todo]:
        """Top-level todos only, each carrying its steps.

        ``completed`` and ``category`` filter the *parent* row — steps have their
        own completion state (they are independent), so filtering on them would
        make a parent appear or vanish based on its children. Pagination likewise
        counts parents, so one page can hold more rows than its page size.
        """
        stmt = (
            select(Todo)
            .where(Todo.user_id == user_id, Todo.parent_id.is_(None))
            .options(selectinload(Todo.children))
        )
        if completed is not None:
            stmt = stmt.where(
                Todo.completed_at.is_(None) if not completed else Todo.completed_at.is_not(None)
            )
        if category:
            stmt = stmt.where(Todo.category == category)
        stmt = (
            stmt.order_by(Todo.completed_at.is_(None).desc(), Todo.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await session.scalars(stmt)).unique())

    async def update(self, session: AsyncSession, todo: Todo, **fields) -> Todo:
        for k, v in fields.items():
            setattr(todo, k, v)
        await session.flush()
        return todo

    async def delete(self, session: AsyncSession, user_id: str, todo_id: str) -> bool:
        """Delete a todo together with its steps.

        The steps are removed explicitly rather than left to the column's
        ``ondelete="CASCADE"``: this project never issues ``PRAGMA
        foreign_keys=ON``, and SQLite defaults foreign keys **off**, so the
        database would not cascade. A leftover step would keep a dangling
        ``parent_id`` and, because the tree query only reads top-level rows, it
        would be invisible while still occupying a row.
        """
        owned = select(Todo.id).where(Todo.id == todo_id, Todo.user_id == user_id)
        await session.execute(delete(Todo).where(Todo.parent_id.in_(owned)))
        result = await session.execute(
            delete(Todo).where(Todo.id == todo_id, Todo.user_id == user_id)
        )
        return result.rowcount > 0

    async def list_metrics(self, session: AsyncSession, todo_id: str) -> list[TodoMetric]:
        """Retained with the metrics table; no API exposes these any more."""
        stmt = (
            select(TodoMetric)
            .where(TodoMetric.todo_id == todo_id)
            .order_by(TodoMetric.created_at)
        )
        return list((await session.scalars(stmt)).unique())
