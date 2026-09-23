from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ConversationRepository:
    async def create(self, session: AsyncSession, conversation) -> object:
        session.add(conversation)
        await session.flush()
        return conversation

    async def get(self, session: AsyncSession, user_id: str, conversation_id: str):
        from app.models.conversation import Conversation

        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
        return await session.scalar(stmt)

    async def list(self, session: AsyncSession, user_id: str, limit: int = 50):
        from app.models.conversation import Conversation

        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return list((await session.scalars(stmt)).unique())

    async def list_messages(self, session: AsyncSession, conversation_id: str, limit: int = 200):
        from app.models.conversation import Message

        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list((await session.scalars(stmt)).unique())

    async def add_message(self, session: AsyncSession, message) -> object:
        session.add(message)
        await session.flush()
        return message
