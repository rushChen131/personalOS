from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime.base import AgentContext
from app.ai.tools import action_proposals
from app.ai.tools.registry import ToolRegistry
from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.models.user import User

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/{proposal_id}/confirm")
async def confirm_action(
    proposal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Confirm a pending high-risk proposal and execute it (§67).

    The tool and arguments are taken from the stored proposal — never from a
    fresh model turn — so what the user approved is exactly what runs.
    """
    proposal = action_proposals.confirm(proposal_id, user.id)
    if proposal is None:
        raise NotFoundError(ErrorCode.RESOURCE_NOT_FOUND, "Action proposal not found")

    registry = ToolRegistry()
    context = AgentContext(
        user_id=user.id,
        metadata={"agent_name": proposal.get("agent_name")} if proposal.get("agent_name") else {},
    )
    result = await registry.execute_approved(
        proposal["tool"], proposal.get("arguments") or {}, context, session
    )
    if "error" in result:
        proposal["status"] = "FAILED"
        proposal["error"] = result["error"]
    else:
        proposal["status"] = "EXECUTED"
        proposal["result"] = result
    return ok(request, proposal)
