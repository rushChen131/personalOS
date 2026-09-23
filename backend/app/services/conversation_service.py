from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message
from app.repositories.insight_report_repository import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    async def create(
        self,
        session: AsyncSession,
        user_id: str,
        title: str | None = None,
        context_type: str | None = None,
        context_id: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
            context_type=context_type,
            context_id=context_id,
        )
        return await self.repository.create(session, conversation)

    async def get_or_create_for_context(
        self,
        session: AsyncSession,
        user_id: str,
        context_type: str | None,
        context_id: str | None,
    ) -> Conversation:
        conversation = await self.repository.get(session, user_id, str(context_id) if context_id else "")
        if conversation is None:
            conversation = await self.create(
                session, user_id, context_type=context_type, context_id=context_id
            )
        return conversation

    async def get(self, session: AsyncSession, user_id: str, conversation_id: str) -> Conversation | None:
        return await self.repository.get(session, user_id, conversation_id)

    async def list(self, session: AsyncSession, user_id: str, limit: int = 50) -> list[Conversation]:
        return await self.repository.list(session, user_id, limit)

    async def messages(
        self, session: AsyncSession, conversation_id: str, limit: int = 200
    ) -> list[Message]:
        return await self.repository.list_messages(session, conversation_id, limit)

    async def add_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
    ) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        return await self.repository.add_message(session, message)
