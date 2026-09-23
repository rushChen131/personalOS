from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import event_bus
from app.models.user import User
from app.repositories.journal_repository import JournalRepository
from app.schemas.common import JournalCreate, JournalResponse
from app.services.journal_service import JournalService

router = APIRouter(prefix="/journals", tags=["journals"])

journal_service = JournalService(JournalRepository(), event_bus)


@router.post("")
async def create_journal(
    request: Request,
    body: JournalCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    journal = await journal_service.create(session, user.id, body)
    return ok(request, JournalResponse.model_validate(journal))


@router.get("")
async def list_journals(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    journals = await journal_service.list(session, user.id, limit, offset)
    return ok(request, [JournalResponse.model_validate(j) for j in journals])


@router.get("/{journal_id}")
async def get_journal(
    journal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    journal = await journal_service.get(session, user.id, journal_id)
    if journal is None:
        raise NotFoundError(ErrorCode.JOURNAL_NOT_FOUND, "Journal not found")
    return ok(request, JournalResponse.model_validate(journal))


@router.delete("/{journal_id}")
async def delete_journal(
    journal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    deleted = await journal_service.delete(session, user.id, journal_id)
    if not deleted:
        raise NotFoundError(ErrorCode.JOURNAL_NOT_FOUND, "Journal not found")
    return ok(request, {"deleted": True})
