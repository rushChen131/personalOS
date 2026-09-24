from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.runtime import AgentContext
from app.models.memory import Memory
from app.models.project import Todo
from app.models.user import User

# Page-scoped context recipes (design2.md §53). Each entry lists the extra
# blocks to load on top of the always-present `user` block, so the Copilot
# knows what the user is looking at without them repeating it.
#
# Journals are the only user-authored input, so "what I've been doing" is
# always answered from journals and the memories distilled from them.
PAGE_CONTEXT: dict[str, tuple[str, ...]] = {
    "dashboard": ("memories", "recent_journals", "todos"),
    "todo": ("todo", "recent_journals", "memories"),
    "todos": ("todos", "recent_journals"),
    "journal": ("recent_journals", "memories"),
    "journals": ("recent_journals",),
    "memory": ("memories", "recent_journals"),
    "memories": ("memories", "recent_journals"),
}

_LIMIT = 10


class ContextRuntime:
    """Build the compact, user-scoped projection consumed by agents.

    The projection is *page-aware*: a todo page carries the todo plus its
    journals and memories, a memory page carries memories and the journals
    behind them, and so on. Everything is scoped by ``user_id`` and failures
    degrade to a partial context rather than failing the whole run.
    """

    async def build(self, session: AsyncSession, context: AgentContext) -> dict[str, Any]:
        user = await session.get(User, context.user_id)
        payload: dict[str, Any] = {
            "user": self._user_block(user),
            "page": context.current_page,
        }

        page = (context.current_page or "dashboard").lower()
        object_id = context.current_object_id
        wanted = PAGE_CONTEXT.get(page)

        if wanted is None:
            # Unknown page: fall back to a broad snapshot so the Copilot still
            # has something to reason about.
            wanted = ("todos", "memories", "recent_journals")

        if "todo" in wanted:
            payload["todo"] = await self._todo_block(session, context.user_id, object_id)
        if "todos" in wanted:
            payload["todos"] = await self._todos(session, context.user_id)
        if "memories" in wanted:
            payload["memories"] = await self._memories(session, context.user_id)
        if "recent_journals" in wanted:
            payload["recent_journals"] = await self._recent_journals(session, context.user_id)

        return payload

    # ------------------------------------------------------------------ blocks

    @staticmethod
    def _user_block(user: User | None) -> dict[str, Any] | None:
        if user is None:
            return None
        return {"id": user.id, "name": user.name, "timezone": user.timezone, "locale": user.locale}

    async def _todo_block(
        self, session: AsyncSession, user_id: str, todo_id: str | None
    ) -> dict[str, Any] | None:
        if not todo_id:
            return None
        todo = await session.get(Todo, todo_id)
        if todo is None or todo.user_id != user_id:
            return None
        return {
            "id": todo.id,
            "title": todo.title,
            "description": todo.description,
            "category": todo.category,
            "why": todo.why,
            "priority": todo.priority,
            "completed": todo.completed_at is not None,
            "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
            "target_date": todo.target_date.isoformat() if todo.target_date else None,
            # Set when this todo is itself a step of another one.
            "parent_id": todo.parent_id,
            "steps": await self._steps(session, todo.id),
        }

    @staticmethod
    async def _steps(session: AsyncSession, todo_id: str) -> list[dict[str, Any]]:
        """The single level of steps under a todo, in the order written."""
        rows = list(
            (
                await session.scalars(
                    select(Todo).where(Todo.parent_id == todo_id).order_by(Todo.created_at)
                )
            ).unique()
        )
        return [
            {
                "id": step.id,
                "title": step.title,
                "completed": step.completed_at is not None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            }
            for step in rows
        ]

    async def _todos(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        """Top-level todos, each with its steps — a step is never listed alone."""
        rows = list(
            (
                await session.scalars(
                    select(Todo)
                    .where(Todo.user_id == user_id, Todo.parent_id.is_(None))
                    .options(selectinload(Todo.children))
                    .order_by(Todo.completed_at.is_(None).desc(), Todo.created_at.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {
                "id": todo.id,
                "title": todo.title,
                "category": todo.category,
                "completed": todo.completed_at is not None,
                "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
                "steps": [
                    {
                        "id": step.id,
                        "title": step.title,
                        "completed": step.completed_at is not None,
                    }
                    for step in todo.children
                ],
            }
            for todo in rows
        ]

    async def _memories(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        rows = list(
            (
                await session.scalars(
                    select(Memory)
                    .where(Memory.user_id == user_id)
                    .order_by(Memory.importance.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {
                "id": memory.id,
                "content": memory.content,
                "type": memory.type,
                "importance": float(memory.importance or 0),
            }
            for memory in rows
        ]

    async def _recent_journals(self, session: AsyncSession, user_id: str) -> list[dict[str, Any]]:
        from app.models.journal import Journal

        rows = list(
            (
                await session.scalars(
                    select(Journal)
                    .where(Journal.user_id == user_id)
                    .order_by(Journal.created_at.desc())
                    .limit(_LIMIT)
                )
            ).unique()
        )
        return [
            {"id": journal.id, "title": journal.title, "content": (journal.content or "")[:500]}
            for journal in rows
        ]


__all__ = ["ContextRuntime", "PAGE_CONTEXT"]
