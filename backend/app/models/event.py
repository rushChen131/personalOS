from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB, TZDateTime, VectorType
from app.models.base import Base, EventSource, TimestampMixin, uuid_pk


class Event(Base, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("importance >= 0 AND importance <= 1", name="chk_event_importance"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="chk_event_confidence"),
        Index("idx_events_user_time", "user_id", "start_time"),
        Index("idx_events_user_type", "user_id", "type"),
        Index("idx_events_project", "project_id"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    journal_id: Mapped[str | None] = mapped_column(
        ForeignKey("journals.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=EventSource.MANUAL.value
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(nullable=True)
    importance: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="0.5")
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, server_default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")
    embedding: Mapped[list[float] | None] = mapped_column(VectorType(1536), nullable=True)

    user: Mapped[User] = relationship(back_populates="events")
    journal: Mapped[Journal] = relationship(back_populates="events")
    project: Mapped[Project] = relationship(back_populates="events")
    goals: Mapped[list[Goal]] = relationship(secondary="event_goals", back_populates="events")
    tags: Mapped[list[Tag]] = relationship(secondary="event_tags", back_populates="events")


class EventGoal(Base):
    __tablename__ = "event_goals"
    __table_args__ = (Index("idx_event_goals_goal", "goal_id"),)

    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(
        String(32), default="RELATED", server_default="RELATED"
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uk_tags_user_name"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)

    events: Mapped[list[Event]] = relationship(secondary="event_tags", back_populates="tags")


class EventTag(Base):
    __tablename__ = "event_tags"

    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
