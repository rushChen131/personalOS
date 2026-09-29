from __future__ import annotations

from app.core.config import settings


class ModelRouter:
    """Pick a model per task type; mock mode ignores the id but keeps it stable.

    The ids come from settings rather than being hardcoded, because the
    OpenAI-protocol gateway may be pointed at an endpoint that serves entirely
    different models (a company LiteLLM proxy, for instance) — see
    ``OPENAI_CHAT_MODEL`` / ``OPENAI_HEAVY_MODEL``.
    """

    _HEAVY_TASKS = {"coach"}

    def select(self, task_type: str) -> str:
        if settings.llm_provider == "mock":
            return "mock-deterministic-v1"
        if task_type in self._HEAVY_TASKS:
            return settings.openai_heavy_model
        return settings.openai_chat_model
