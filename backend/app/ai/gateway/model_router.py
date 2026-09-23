from __future__ import annotations

from app.core.config import settings


class ModelRouter:
    """Pick a model per task type; mock mode ignores the id but keeps it stable."""

    _CHEAP_TASKS = {"chat", "extract", "memory_refine"}
    _HEAVY_TASKS = {"coach"}

    def select(self, task_type: str) -> str:
        if settings.llm_provider == "mock":
            return "mock-deterministic-v1"
        if task_type in self._CHEAP_TASKS:
            return "gpt-4o-mini"
        if task_type in self._HEAVY_TASKS:
            return "gpt-4o"
        return "gpt-4o-mini"
