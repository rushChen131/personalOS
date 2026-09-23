from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.infrastructure.bus.event_bus import event_bus
from app.models.user import User
from app.repositories.memory_repository import MemoryRepository
from app.schemas.common import MemoryResponse, MemorySearchRequest
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])

memory_service = MemoryService(MemoryRepository(), event_bus)


@router.get("")
async def list_memories(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    memories = await memory_service.list(session, user.id, limit, offset)
    return ok(request, [MemoryResponse.model_validate(m) for m in memories])


@router.post("/search")
async def search_memories(
    request: Request,
    body: MemorySearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    memories = await memory_service.search(session, user.id, body)
    return ok(request, [MemoryResponse.model_validate(m) for m in memories])


@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    memory = await memory_service.get(session, user.id, memory_id)
    if memory is None:
        raise NotFoundError(ErrorCode.MEMORY_NOT_FOUND, "Memory not found")
    return ok(request, MemoryResponse.model_validate(memory))
