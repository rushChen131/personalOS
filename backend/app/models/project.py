from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB, TZDateTime
from app.models.base import Base, Category, TimestampMixin, uuid_pk


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
    todos: Mapped[list[Todo]] = relationship(
        secondary="todo_projects", back_populates="projects"
    )
    events: Mapped[list[Event]] = relationship(back_populates="project")


class Todo(Base, TimestampMixin):
    """A checklist item: a title, a life-domain, and a completion timestamp.

    Completion is a single nullable timestamp rather than a status string plus a
    0-100 progress bar. One source of truth means a row can never disagree with
    itself ("ACTIVE" but 100% done), and "when did I finish this" is answerable
    without a second column.

    A todo may own one level of child todos (`parent_id`), keeping "the thing"
    and "the steps of the thing" in one list. Completion is independent across
    that edge: a finished parent can still have open steps.
    """

    __tablename__ = "todos"
    __table_args__ = (
        Index("idx_todos_user_completed", "user_id", "completed_at"),
        Index("idx_todos_target_date", "user_id", "target_date"),
        Index("idx_todos_user_category", "user_id", "category"),
        Index("idx_todos_parent", "parent_id"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # NULL = a top-level todo; otherwise the todo is a step of `parent_id`.
    # The depth is capped at ONE level by `TodoService.create` — a portable
    # self-referential CHECK cannot be expressed in SQLite, so the rule lives in
    # the service rather than the schema.
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("todos.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=Category.OTHER.value
    )
    priority: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # NULL = still open; a timestamp = done, and the timestamp is when.
    completed_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    user: Mapped[User] = relationship(back_populates="todos")
    metrics: Mapped[list[TodoMetric]] = relationship(
        back_populates="todo", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(
        secondary="todo_projects", back_populates="todos"
    )
    events: Mapped[list[Event]] = relationship(secondary="event_todos", back_populates="todos")
    # One level of steps. `delete-orphan` covers ORM deletes; `TodoRepository`
    # also deletes children explicitly, because SQLite runs with foreign keys
    # OFF and the column's ondelete="CASCADE" never fires on a bulk DELETE.
    children: Mapped[list[Todo]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        # Steps keep the order they were written in. The top-level list sorts
        # "open first, newest first", but reordering steps under a parent would
        # make a checklist jump around as items get ticked.
        order_by="Todo.created_at",
    )
    parent: Mapped[Todo | None] = relationship(back_populates="children", remote_side=[id])


class TodoMetric(Base, TimestampMixin):
    """Retained with the old Goal module's metrics table.

    The metrics API was removed when goals became todos (a checklist has no
    progress to measure), but the model and table stay so the rows survive and
    the mapper keeps resolving.
    """

    __tablename__ = "todo_metrics"
    __table_args__ = (Index("idx_todo_metrics_todo", "todo_id"),)

    id: Mapped[str] = uuid_pk()
    todo_id: Mapped[str] = mapped_column(
        ForeignKey("todos.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_value: Mapped[float | None] = mapped_column(nullable=True)
    target_value: Mapped[float | None] = mapped_column(nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight: Mapped[float] = mapped_column(nullable=False, default=1, server_default="1")
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, name="metadata")

    todo: Mapped[Todo] = relationship(back_populates="metrics")


class TodoProject(Base):
    __tablename__ = "todo_projects"

    todo_id: Mapped[str] = mapped_column(
        ForeignKey("todos.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(
        String(32), default="RELATED", server_default="RELATED"
    )
