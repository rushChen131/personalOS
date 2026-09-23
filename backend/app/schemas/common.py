from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    source: str = "MANUAL"
    mood: str | None = None
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JournalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    content: str
    source: str
    mood: str | None
    occurred_at: datetime | None
    created_at: datetime


class GoalCreate(BaseModel):
    title: str
    description: str | None = None
    why: str | None = None
    priority: int = 0
    start_date: date | None = None
    target_date: date | None = None


class GoalUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    why: str | None = None
    status: str | None = None
    priority: int | None = None
    start_date: date | None = None
    target_date: date | None = None
    progress: float | None = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    why: str | None
    status: str
    priority: int
    progress: float
    start_date: date | None
    target_date: date | None
    created_at: datetime


class MetricCreate(BaseModel):
    name: str
    metric_type: str
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    weight: float = 1


class MetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    goal_id: str
    name: str
    metric_type: str
    current_value: float | None
    target_value: float | None
    unit: str | None
    weight: float


class MemorySearchRequest(BaseModel):
    query: str | None = None
    memory_type: str | None = None
    importance_min: float | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = 20
    offset: int = 0


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
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


class ContextResponse(BaseModel):
    page: str
    object: dict[str, str | None]
    related_journals: list[JournalResponse] = Field(default_factory=list)
    related_memories: list[MemoryResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    database: str
    version: str
