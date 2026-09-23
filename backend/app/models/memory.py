from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB, TZDateTime, VectorType
from app.models.base import Base, CandidateStatus, MemoryType, TimestampMixin, uuid_pk


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"
    __table_args__ = (
        Index("idx_memories_user_type", "user_id", "type"),
        Index("idx_memories_user_importance", "user_id", "importance"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=MemoryType.FACT.value)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.5")
    importance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.5")
    source_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    valid_from: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(1536), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    user: Mapped[User] = relationship(back_populates="memories")
    sources: Mapped[list[MemorySource]] = relationship(
        back_populates="memory", cascade="all, delete-orphan"
    )


class MemorySource(Base, TimestampMixin):
    __tablename__ = "memory_sources"
    __table_args__ = (
        Index("idx_memory_sources_memory", "memory_id"),
        Index("idx_memory_sources_source", "source_type", "source_id"),
    )

    id: Mapped[str] = uuid_pk()
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(nullable=False)
    relevance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="1")

    memory: Mapped[Memory] = relationship(back_populates="sources")


class MemoryCandidate(Base, TimestampMixin):
    """Staging row between Event and Memory (技术设计.md §83).

    Events never become Memory directly. Each event first accumulates
    evidence in a candidate bucket; only when ``confidence`` crosses the
    promotion threshold and enough independent events agree does the
    MemoryEngine promote the bucket into a real ``Memory`` row.
    """

    __tablename__ = "memory_candidates"
    __table_args__ = (
        UniqueConstraint("user_id", "signature", name="uq_memory_candidates_user_signature"),
        Index("idx_memory_candidates_user_status", "user_id", "status"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Bucket key: normalised topic + memory type, e.g. "AI AGENT|PATTERN".
    signature: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=MemoryType.PATTERN.value)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=CandidateStatus.PENDING.value
    )
    # Distinct normalised event titles seen for this bucket.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    promoted_memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)

    user: Mapped[User] = relationship()
