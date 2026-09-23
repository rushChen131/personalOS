from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.ai.runtime.base import (
    READ,
    WRITE_INSIGHT,
    WRITE_MEMORY,
    AgentContext,
    AgentInput,
    AgentResult,
)

if TYPE_CHECKING:
    from app.ai.runtime.runtime import AgentRuntime

__all__ = [
    "READ",
    "WRITE_INSIGHT",
    "WRITE_MEMORY",
    "AgentContext",
    "AgentInput",
    "AgentResult",
    "AgentRuntime",
    "sse",
]


def __getattr__(name: str) -> Any:
    """Lazily resolve AgentRuntime/sse to avoid an import cycle with app.ai.tools."""
    if name in {"AgentRuntime", "sse"}:
        from app.ai.runtime import runtime as _runtime

        return getattr(_runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
