from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import event_bus
from app.models.user import User
from app.repositories.goal_repository import GoalRepository
from app.schemas.common import (
    GoalCreate,
    GoalResponse,
    GoalUpdate,
    MetricCreate,
    MetricResponse,
)
from app.services.goal_service import GoalService

router = APIRouter(prefix="/goals", tags=["goals"])

goal_service = GoalService(GoalRepository(), event_bus)


async def _to_response(goal, session):
    return GoalResponse(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        why=goal.why,
        status=goal.status,
        priority=goal.priority,
        progress=float(goal.progress) if goal.progress is not None else 0.0,
        start_date=goal.start_date,
        target_date=goal.target_date,
        created_at=goal.created_at,
    )


@router.post("")
async def create_goal(
    request: Request,
    body: GoalCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    goal = await goal_service.create(session, user.id, body)
    return ok(request, await _to_response(goal, session))


@router.get("")
async def list_goals(
    request: Request,
    status: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    goals = await goal_service.list(session, user.id, status)
    return ok(request, [await _to_response(g, session) for g in goals])


@router.get("/{goal_id}")
async def get_goal(
    goal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    goal = await goal_service.get(session, user.id, goal_id)
    if goal is None:
        raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, "Goal not found")
    return ok(request, await _to_response(goal, session))


@router.put("/{goal_id}")
async def update_goal(
    goal_id: str,
    request: Request,
    body: GoalUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    goal = await goal_service.update(session, user.id, goal_id, body)
    if goal is None:
        raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, "Goal not found")
    return ok(request, await _to_response(goal, session))


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    deleted = await goal_service.delete(session, user.id, goal_id)
    if not deleted:
        raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, "Goal not found")
    return ok(request, {"deleted": True})


@router.post("/{goal_id}/metrics")
async def add_metric(
    goal_id: str,
    request: Request,
    body: MetricCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    metric = await goal_service.add_metric(session, user.id, goal_id, body)
    if metric is None:
        raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, "Goal not found")
    return ok(request, MetricResponse.model_validate(metric))
