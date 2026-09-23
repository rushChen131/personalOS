from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.database import TZDateTime, UUIDType


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def uuid_pk():
    return mapped_column(UUIDType(), primary_key=True, default=lambda: str(uuid4()))


class UserStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETED = "DELETED"


class EventType(str, Enum):
    WORK = "WORK"
    LEARNING = "LEARNING"
    LIFE = "LIFE"
    HEALTH = "HEALTH"
    FINANCE = "FINANCE"
    SOCIAL = "SOCIAL"
    TRAVEL = "TRAVEL"
    PROJECT = "PROJECT"
    THOUGHT = "THOUGHT"
    DECISION = "DECISION"
    ACHIEVEMENT = "ACHIEVEMENT"
    FAILURE = "FAILURE"
    OTHER = "OTHER"


class EventSource(str, Enum):
    MANUAL = "MANUAL"
    CHAT = "CHAT"
    CALENDAR = "CALENDAR"
    GIT = "GIT"
    TODO = "TODO"
    EMAIL = "EMAIL"
    HEALTH = "HEALTH"
    LOCATION = "LOCATION"
    BROWSER = "BROWSER"
    AI = "AI"
    IMPORT = "IMPORT"
    API = "API"


class MemoryType(str, Enum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    DECISION = "DECISION"
    EXPERIENCE = "EXPERIENCE"
    SKILL = "SKILL"
    BELIEF = "BELIEF"
    PATTERN = "PATTERN"
    RELATIONSHIP = "RELATIONSHIP"
    GOAL_CONTEXT = "GOAL_CONTEXT"
    PROJECT_CONTEXT = "PROJECT_CONTEXT"


class CandidateStatus(str, Enum):
    """Lifecycle of a pending memory candidate (技术设计.md §83)."""

    PENDING = "PENDING"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class InsightType(str, Enum):
    TREND = "TREND"
    PATTERN = "PATTERN"
    RISK = "RISK"
    ACHIEVEMENT = "ACHIEVEMENT"
    ANOMALY = "ANOMALY"
    GOAL_PROGRESS = "GOAL_PROGRESS"
    BEHAVIOR_CHANGE = "BEHAVIOR_CHANGE"
    SUGGESTION = "SUGGESTION"


class ReportType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    YEARLY = "YEARLY"
    CUSTOM = "CUSTOM"


class MetricType(str, Enum):
    NUMBER = "NUMBER"
    PERCENT = "PERCENT"
    BOOLEAN = "BOOLEAN"
    COUNT = "COUNT"
    TIME = "TIME"
    SCORE = "SCORE"
    CUSTOM = "CUSTOM"
