from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import AgentContext, AgentInput, AgentRuntime, sse
from app.api.deps import get_current_user
from app.api.v1.responses import ok
from app.core.database import get_db
from app.core.errors import ErrorCode, NotFoundError
from app.models.user import User
from app.repositories.insight_report_repository import ConversationRepository
from app.schemas.common import (
    ChatRequest,
    ConversationResponse,
    MessageResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/chat", tags=["chat"])

conversation_service = ConversationService(ConversationRepository())
agent_runtime = AgentRuntime()


def _select_agent(message: str, context_type: str | None) -> str:
    """Route to the most specific agent for the request shape."""
    lowered = message.lower()
    journal_signals = (
        "research",
        "研究",
        "study",
        "studied",
        "learn",
        "learned",
        "reading",
        "read ",
        "log ",
        "spent",
        "for 2 hours",
        "for 3 hours",
        "小时",
    )
    if context_type == "journal" or any(word in lowered for word in journal_signals):
        return "journal_agent"
    if any(word in lowered for word in ("goal", "目标", "progress", "进度")):
        return "goal_agent"
    if any(word in lowered for word in ("memory", "记忆", "remember")):
        return "memory_agent"
    return "personal_manager"


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Run the selected agent and stream its lifecycle as SSE events."""
    conversation = None
    if body.conversation_id:
        conversation = await conversation_service.get(session, user.id, body.conversation_id)
    if conversation is None:
        conversation = await conversation_service.create(
            session,
            user.id,
            context_type=body.context.type,
            context_id=body.context.id,
        )
    await conversation_service.add_message(session, conversation.id, "user", body.message)
    context = AgentContext(
        user_id=user.id,
        conversation_id=conversation.id,
        current_page=body.context.type,
        current_object_id=body.context.id,
    )
    agent_name = _select_agent(body.message, body.context.type)

    async def stream():
        yield sse("start", {"conversation_id": conversation.id, "agent": agent_name})

        async def emit(event: str, data: dict) -> None:
            queue.put_nowait(sse(event, data))

        import asyncio

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        task = asyncio.create_task(
            agent_runtime.run(agent_name, context, AgentInput(body.message), session, emit=emit)
        )
        while not task.done() or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.05)
            except TimeoutError:
                continue
            yield item
        try:
            result = await task
        except Exception as exc:  # pragma: no cover - provider dependent
            yield sse("error", {"message": str(exc)})
            return
        await conversation_service.add_message(session, conversation.id, "assistant", result.content)
        yield sse("content", {"content": result.content})
        yield sse(
            "done",
            {
                "conversation_id": conversation.id,
                "success": result.success,
                "agent": result.metadata.get("agent", agent_name),
            },
        )

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/conversations")
async def create_conversation(
    request: Request,
    title: str | None = None,
    context_type: str | None = None,
    context_id: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversation = await conversation_service.create(session, user.id, title, context_type, context_id)
    return ok(request, ConversationResponse.model_validate(conversation))


@router.get("/conversations")
async def list_conversations(
    request: Request,
    limit: int = 50,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversations = await conversation_service.list(session, user.id, limit)
    return ok(request, [ConversationResponse.model_validate(c) for c in conversations])


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    conversation = await conversation_service.get(session, user.id, conversation_id)
    if conversation is None:
        raise NotFoundError(ErrorCode.RESOURCE_NOT_FOUND, "Conversation not found")
    messages = await conversation_service.messages(session, conversation_id)
    return ok(
        request,
        {
            "conversation": ConversationResponse.model_validate(conversation),
            "messages": [MessageResponse.model_validate(m) for m in messages],
        },
    )
