from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB, TZDateTime, VectorType
from app.models.base import Base, EventSource, TimestampMixin, uuid_pk


class Journal(Base, TimestampMixin):
    __tablename__ = "journals"
    __table_args__ = (Index("idx_journals_user_created", "user_id", "created_at"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=EventSource.MANUAL.value
    )
    mood: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(1536), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    user: Mapped[User] = relationship(back_populates="journals")
    events: Mapped[list[Event]] = relationship(back_populates="journal")
