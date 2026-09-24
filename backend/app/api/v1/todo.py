from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import event_bus
from app.models.base import Category
from app.models.project import Todo
from app.models.user import User
from app.repositories.todo_repository import TodoRepository
from app.schemas.common import TodoCreate, TodoResponse, TodoUpdate
from app.services.todo_service import TodoService

router = APIRouter(prefix="/todos", tags=["todos"])

todo_service = TodoService(TodoRepository(), event_bus)


def _to_response(todo: Todo, children: Sequence[Todo] = ()) -> TodoResponse:
    """Serialise a todo, plus its steps when the caller loaded them.

    `children` is passed in rather than read off `todo.children` so an
    un-eager-loaded relationship can never be touched here — under asyncio that
    would raise `MissingGreenlet` instead of quietly loading.
    """
    return TodoResponse(
        id=todo.id,
        title=todo.title,
        description=todo.description,
        why=todo.why,
        category=todo.category,
        priority=todo.priority,
        start_date=todo.start_date,
        target_date=todo.target_date,
        completed_at=todo.completed_at,
        created_at=todo.created_at,
        parent_id=todo.parent_id,
        children=[_to_response(child) for child in children],
    )


@router.post("")
async def create_todo(
    request: Request,
    body: TodoCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a todo. Send ``parent_id`` to make it a step of another one."""
    todo = await todo_service.create(session, user.id, body)
    return ok(request, _to_response(todo))


@router.get("")
async def list_todos(
    request: Request,
    completed: bool | None = Query(
        default=None, description="true = only done, false = only open, omit for both"
    ),
    category: Category | None = Query(
        default=None, description="A life-domain value; an unknown one is a 422"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List top-level todos, open ones first, each with its steps.

    Steps are never returned as top-level rows — they only ever appear inside
    their parent's ``children``. The filters apply to the parent row, because a
    step keeps its own completion state.
    """
    todos = await todo_service.list_tree(
        session, user.id, completed, category.value if category is not None else None
    )
    return ok(request, [_to_response(todo, todo.children) for todo in todos])


@router.get("/{todo_id}")
async def get_todo(
    todo_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    todo = await todo_service.get_with_children(session, user.id, todo_id)
    if todo is None:
        raise NotFoundError(ErrorCode.TODO_NOT_FOUND, "Todo not found")
    return ok(request, _to_response(todo, todo.children))


@router.put("/{todo_id}")
async def update_todo(
    todo_id: str,
    request: Request,
    body: TodoUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Also the check/uncheck endpoint: send ``{"completed": true|false}``.

    Ticking a parent does not touch its steps, and ticking a step does not move
    its parent — completion is independent across that edge.
    """
    todo = await todo_service.update(session, user.id, todo_id, body)
    if todo is None:
        raise NotFoundError(ErrorCode.TODO_NOT_FOUND, "Todo not found")
    return ok(request, _to_response(todo))


@router.delete("/{todo_id}")
async def delete_todo(
    todo_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete a todo; its steps are deleted with it."""
    deleted = await todo_service.delete(session, user.id, todo_id)
    if not deleted:
        raise NotFoundError(ErrorCode.TODO_NOT_FOUND, "Todo not found")
    return ok(request, {"deleted": True})
