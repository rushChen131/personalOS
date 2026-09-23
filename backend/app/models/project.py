from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB
from app.models.base import Base, TimestampMixin, uuid_pk


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (Index("idx_projects_user_status", "user_id", "status"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    priority: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    user: Mapped[User] = relationship(back_populates="projects")
    goals: Mapped[list[Goal]] = relationship(
        secondary="goal_projects", back_populates="projects"
    )
    events: Mapped[list[Event]] = relationship(back_populates="project")


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"
    __table_args__ = (
        Index("idx_goals_user_status", "user_id", "status"),
        Index("idx_goals_target_date", "user_id", "target_date"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="chk_goal_progress"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="ACTIVE")
    priority: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 0-100 scale per 技术设计.md §12 (NUMERIC(5,2), CHECK 0..100).
    progress: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=0, server_default="0"
    )
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    user: Mapped[User] = relationship(back_populates="goals")
    metrics: Mapped[list[GoalMetric]] = relationship(
        back_populates="goal", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        secondary="goal_projects", back_populates="goals"
    )
    events: Mapped[list[Event]] = relationship(secondary="event_goals", back_populates="goals")


class GoalMetric(Base, TimestampMixin):
    __tablename__ = "goal_metrics"
    __table_args__ = (Index("idx_goal_metrics_goal", "goal_id"),)

    id: Mapped[str] = uuid_pk()
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_value: Mapped[float | None] = mapped_column(nullable=True)
    target_value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight: Mapped[float] = mapped_column(nullable=False, default=1, server_default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    goal: Mapped[Goal] = relationship(back_populates="metrics")


class GoalProject(Base):
    __tablename__ = "goal_projects"

    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(
        String(32), default="RELATED", server_default="RELATED"
    )
