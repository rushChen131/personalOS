from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

READ = "READ"
WRITE_MEMORY = "WRITE_MEMORY"


@dataclass(slots=True)
class AgentContext:
    user_id: str
    conversation_id: str | None = None
    current_page: str = "chat"
    current_object_type: str | None = None
    current_object_id: str | None = None
    goal_ids: list[str] = field(default_factory=list)
    project_ids: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentInput:
    message: str
    variables: dict[str, Any] = field(default_factory=dict)
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AgentResult:
    success: bool
    content: str
    structured_output: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
