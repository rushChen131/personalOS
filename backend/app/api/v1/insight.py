from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import event_bus
from app.models.user import User
from app.repositories.insight_report_repository import InsightRepository
from app.schemas.common import InsightResponse
from app.services.insight_service import InsightService

router = APIRouter(prefix="/insights", tags=["insights"])

insight_service = InsightService(InsightRepository(), event_bus)


@router.get("")
async def list_insights(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    insights = await insight_service.list(session, user.id, limit, offset)
    return ok(request, [InsightResponse.model_validate(i) for i in insights])


@router.get("/{insight_id}")
async def get_insight(
    insight_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    insight = await insight_service.get(session, user.id, insight_id)
    if insight is None:
        raise NotFoundError(ErrorCode.RESOURCE_NOT_FOUND, "Insight not found")
    return ok(request, InsightResponse.model_validate(insight))
