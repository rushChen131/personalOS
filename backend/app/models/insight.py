from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import JSONB, TZDateTime, VectorType
from app.models.base import Base, TimestampMixin, uuid_pk


class Insight(Base, TimestampMixin):
    __tablename__ = "insights"
    __table_args__ = (Index("idx_insights_user_date", "user_id", "discovered_at"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    insight_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.5")
    importance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.5")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    evidence: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(1536), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(
        TZDateTime(), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
