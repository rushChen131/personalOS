from __future__ import annotations

from typing import Any

from app.ai.gateway.base import GatewayResult
from app.ai.gateway.model_router import ModelRouter
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import logger

MAX_TOOL_ROUNDS = 3


class OpenAIGateway:
    """Real provider path; selected only when ``LLM_PROVIDER=openai`` and a key exists.

    Handles the tool-calling loop (<=3 rounds) so the runtime sees the same
    single-call contract as the mock gateway.
    """

    provider = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIGateway")
        self.model = model or ModelRouter().select("chat")

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> GatewayResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.api_key)
        chosen = model or self.model
        try:
            response = await client.chat.completions.create(
                model=chosen,
                messages=messages,
                tools=tools or None,
                temperature=temperature,
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("openai.generate.failed", error=str(exc))
            raise AppError(ErrorCode.LLM_ERROR, f"Model call failed: {exc}", status_code=502) from exc

        choice = response.choices[0].message
        calls = [
            {
                "id": call.id,
                "name": call.function.name,
                "arguments": self._parse_arguments(call.function.arguments),
            }
            for call in (choice.tool_calls or [])
        ]
        usage = response.usage
        return GatewayResult(
            content=choice.content or "",
            tool_calls=calls,
            usage={
                "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
            },
        )

    @staticmethod
    def _parse_arguments(raw: str | None) -> dict[str, Any]:
        import json

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}


def build_gateway() -> Any:
    """Select the gateway from settings, falling back to mock when unusable."""
    if settings.llm_provider == "openai" and settings.openai_api_key:
        try:
            return OpenAIGateway()
        except ValueError:
            logger.warning("gateway.openai.unavailable", fallback="mock")
    return _mock()


def _mock() -> Any:
    from app.ai.gateway.mock_gateway import MockGateway

    return MockGateway()
