from __future__ import annotations

from typing import Any

from app.ai.gateway.base import GatewayResult
from app.ai.gateway.model_router import ModelRouter
from app.core.config import settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import logger


class OpenAIGateway:
    """Real provider path; selected only when ``LLM_PROVIDER=openai`` and a key exists.

    Speaks the OpenAI *protocol*, not necessarily OpenAI *the service*: with
    ``OPENAI_BASE_URL`` set it talks to any compatible endpoint, and the model
    ids come from ``OPENAI_CHAT_MODEL`` / ``OPENAI_HEAVY_MODEL``.

    One call per invocation — the tool-calling loop (<=3 rounds) belongs to
    ``app.ai.runtime.runtime``, so this stays a plain request/response gateway
    and the runtime sees one contract from every provider.
    """

    provider = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIGateway")
        self.base_url = base_url or settings.openai_base_url
        self.model = model or ModelRouter().select("chat")

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> GatewayResult:
        from openai import AsyncOpenAI

        # `base_url=None` makes the SDK fall back to its own default, so an
        # unset OPENAI_BASE_URL keeps the original behaviour exactly.
        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url or None)
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
            gateway = OpenAIGateway()
        except ValueError:
            logger.warning("gateway.openai.unavailable", fallback="mock")
        else:
            # Logged because "which endpoint am I actually hitting" is the first
            # question whenever a reply looks wrong.
            logger.info(
                "gateway.openai.selected",
                model=gateway.model,
                base_url=gateway.base_url or "sdk-default",
            )
            return gateway
    return _mock()


def _mock() -> Any:
    from app.ai.gateway.mock_gateway import MockGateway

    return MockGateway()
