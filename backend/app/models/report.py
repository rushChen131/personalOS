from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSONB
from app.models.base import Base, TimestampMixin, uuid_pk


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (
        Index("idx_reports_user_period", "user_id", "period_end"),
        Index("idx_reports_user_type", "user_id", "type"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_definitions.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False, server_default="ALL")
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="COMPLETED")

    definition: Mapped[ReportDefinition] = relationship(back_populates="reports")


class ReportDefinition(Base, TimestampMixin):
    __tablename__ = "report_definitions"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False, server_default="ALL")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sections: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")

    reports: Mapped[list[Report]] = relationship(back_populates="definition")
