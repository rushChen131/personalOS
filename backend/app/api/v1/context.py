from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import ContextResponse
from app.services.context_service import ContextService

router = APIRouter(prefix="/context", tags=["context"])

context_service = ContextService()


@router.get("")
async def get_context(
    request: Request,
    page: str = "dashboard",
    object_type: str | None = None,
    object_id: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ctx: ContextResponse = await context_service.build(
        session, user.id, page, object_type, object_id
    )
    return ok(request, ctx)
