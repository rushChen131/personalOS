from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import EventBus
from app.models.base import coerce_category
from app.models.project import Todo
from app.repositories.todo_repository import TodoRepository
from app.schemas.common import TodoCreate, TodoUpdate


class TodoService:
    def __init__(self, repository: TodoRepository, bus: EventBus | None = None):
        self.repository = repository
        self.bus = bus

    async def create(self, session: AsyncSession, user_id: str, data: TodoCreate) -> Todo:
        """Create a todo, or a step of one when ``parent_id`` is set.

        A step is deliberately thin: it takes its category and target date from
        the parent, so the two can never disagree about which area of life the
        work belongs to. Depth is capped at one level here rather than in the
        schema, because SQLite cannot express a portable self-referential CHECK.
        """
        parent: Todo | None = None
        if data.parent_id is not None:
            parent = await self.repository.get(session, user_id, data.parent_id)
            if parent is None:
                # Also covers another user's todo: answering 404 rather than 403
                # avoids confirming that the id exists at all.
                raise NotFoundError(ErrorCode.TODO_NOT_FOUND, "Parent todo not found")
            if parent.parent_id is not None:
                raise AppError(
                    ErrorCode.VALIDATION_ERROR,
                    "A step cannot own steps (nesting is limited to one level)",
                )

        todo = Todo(
            user_id=user_id,
            parent_id=parent.id if parent is not None else None,
            title=data.title,
            description=data.description,
            why=data.why,
            category=parent.category if parent is not None else coerce_category(data.category),
            priority=data.priority,
            start_date=data.start_date,
            target_date=parent.target_date if parent is not None else data.target_date,
        )
        todo = await self.repository.create(session, todo)
        await session.flush()
        if self.bus is not None:
            await self.bus.publish("TodoCreated", {"todo_id": todo.id, "user_id": user_id})
        return todo

    async def get(self, session: AsyncSession, user_id: str, todo_id: str) -> Todo | None:
        return await self.repository.get(session, user_id, todo_id)

    async def get_with_children(
        self, session: AsyncSession, user_id: str, todo_id: str
    ) -> Todo | None:
        return await self.repository.get_with_children(session, user_id, todo_id)

    async def list(
        self,
        session: AsyncSession,
        user_id: str,
        completed: bool | None = None,
        category: str | None = None,
    ) -> list[Todo]:
        """Flat list — every todo, steps included. See :meth:`list_tree`."""
        return await self.repository.list(session, user_id, completed, category)

    async def list_tree(
        self,
        session: AsyncSession,
        user_id: str,
        completed: bool | None = None,
        category: str | None = None,
    ) -> list[Todo]:
        """Top-level todos with their steps attached."""
        return await self.repository.list_tree(session, user_id, completed, category)

    async def update(
        self, session: AsyncSession, user_id: str, todo_id: str, data: TodoUpdate
    ) -> Todo | None:
        todo = await self.repository.get(session, user_id, todo_id)
        if todo is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        if fields.get("category") is not None:
            # Pydantic hands back the enum member; store the plain string.
            fields["category"] = coerce_category(fields["category"])

        if todo.parent_id is not None:
            # A step inherits these two from its parent, so they are not its to
            # set — same rule as `create`, and it keeps the pair consistent.
            fields.pop("category", None)
            fields.pop("target_date", None)

        # `completed` is intent; `completed_at` is the record. The server owns the
        # clock so a device with a skewed clock cannot write a wrong timestamp.
        # Completion is independent across the parent/child edge: ticking a
        # parent leaves its steps alone, and vice versa.
        completed = fields.pop("completed", None)
        if completed is not None:
            fields["completed_at"] = datetime.now(timezone.utc) if completed else None

        todo = await self.repository.update(session, todo, **fields)
        if self.bus is not None:
            await self.bus.publish("TodoUpdated", {"todo_id": todo.id, "user_id": user_id})
        return todo

    async def delete(self, session: AsyncSession, user_id: str, todo_id: str) -> bool:
        """Delete a todo; its steps go with it."""
        return await self.repository.delete(session, user_id, todo_id)
