from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB
from app.models.base import Base, TimestampMixin, UserStatus, uuid_pk


class User(Base, TimestampMixin):
    __tablename__ = "users"
    # §8: the email uniqueness is a *partial* index scoped to live rows, so a
    # soft-deleted user's email can be reused by a new registration.
    __table_args__ = (
        Index(
            "uk_users_email",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = uuid_pk()
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Tokyo")
    locale: Mapped[str] = mapped_column(String(32), nullable=False, server_default="zh-CN")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=UserStatus.ACTIVE.value)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    settings: Mapped[UserSetting] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    goals: Mapped[list[Goal]] = relationship(back_populates="user", cascade="all, delete-orphan")
    projects: Mapped[list[Project]] = relationship(back_populates="user", cascade="all, delete-orphan")
    journals: Mapped[list[Journal]] = relationship(back_populates="user", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[list[Memory]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSetting(Base, TimestampMixin):
    __tablename__ = "user_settings"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    daily_reminder_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    weekly_report_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    monthly_report_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    ai_memory_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    ai_auto_insight_enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    theme: Mapped[str] = mapped_column(String(32), default="system")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates="settings")
