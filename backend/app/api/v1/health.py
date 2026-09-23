from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.responses import ok
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request, session: AsyncSession = Depends(get_db)):
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "error"
    return ok(
        request,
        {
            "status": "ok",
            "database": database,
            "version": settings.app_version,
            "provider": settings.llm_provider,
        },
    )
