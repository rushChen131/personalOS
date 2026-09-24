from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.base import Category, ReportType


class ApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    data: Any = None
    request_id: str | None = None


class ApiError(BaseModel):
    code: str
    message: str


class ApiErrorResponse(BaseModel):
    success: bool = False
    error: ApiError
    request_id: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str | None
    name: str
    timezone: str
    locale: str


class JournalCreate(BaseModel):
    title: str | None = None
    content: str
    # Typed as the enum so an unknown domain is rejected with a 422 rather
    # than silently written into the table.
    category: Category = Category.OTHER
    source: str = "MANUAL"
    mood: str | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JournalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    content: str
    category: str
    source: str
    mood: str | None
    occurred_at: datetime | None
    created_at: datetime


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    why: str | None = None
    category: Category = Category.OTHER
    priority: int = 0
    start_date: date | None = None
    target_date: date | None = None
    # Set to make this todo a step of another one. The parent must itself be
    # top-level (depth is capped at one level), and its category/target_date win
    # over anything sent here — see `TodoService.create`.
    parent_id: str | None = None


class TodoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    why: str | None = None
    category: Category | None = None
    priority: int | None = None
    start_date: date | None = None
    target_date: date | None = None
    # Check/uncheck. True stamps `completed_at` server-side, False clears it.
    completed: bool | None = None
    # `parent_id` is deliberately absent: re-parenting a todo is not supported,
    # so a todo is created under a parent and stays there.


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    why: str | None
    category: str
    priority: int
    start_date: date | None
    target_date: date | None
    # NULL = open. A timestamp means done, and the value is when.
    completed_at: datetime | None
    created_at: datetime
    # NULL = a top-level todo. `children` is only populated on top-level rows;
    # a child never has children of its own (depth is capped at one level).
    parent_id: str | None = None
    children: list[TodoResponse] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str | None = None
    memory_type: str | None = None
    category: Category | None = None
    importance_min: float | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = 20
    offset: int = 0


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    category: str
    content: str
    summary: str | None
    confidence: float
    importance: float
    source_count: int
    valid_from: datetime | None
    valid_to: datetime | None
    last_verified_at: datetime | None
    created_at: datetime


class ChatContext(BaseModel):
    type: str = "dashboard"
    id: str | None = None


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    context: ChatContext = ChatContext()


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    context_type: str | None
    context_id: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class ReportGenerateRequest(BaseModel):
    """Ask the engine to build, or refresh, one period report.

    ``period_start`` / ``period_end`` are optional. When omitted the engine uses
    the period containing *today in UTC* — this platform has no ``tzdata``, so
    UTC is the only calendar available. Clients that know the user's real local
    date (the frontend does) should pass explicit bounds.

    ``dimension`` scopes the report to one life domain (``Category``); omitting
    it covers every domain.
    """

    #: Only the three periods the engine can aggregate.
    SUPPORTED: ClassVar[set[ReportType]] = {
        ReportType.DAILY,
        ReportType.WEEKLY,
        ReportType.MONTHLY,
    }

    type: ReportType = ReportType.DAILY
    dimension: Category | None = None
    period_start: date | None = None
    period_end: date | None = None

    @field_validator("type")
    @classmethod
    def _supported_type(cls, value: ReportType) -> ReportType:
        if value not in cls.SUPPORTED:
            raise ValueError("supported types: DAILY, WEEKLY, MONTHLY")
        return value


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    #: ``ALL`` or a ``Category`` value — see ``ReportGenerateRequest.dimension``.
    dimension: str
    period_start: date
    period_end: date
    title: str
    summary: str | None
    content: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class ContextResponse(BaseModel):
    page: str
    object: dict[str, str | None]
    related_journals: list[JournalResponse] = Field(default_factory=list)
    related_memories: list[MemoryResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    database: str
    version: str
