from __future__ import annotations

from typing import Any, Protocol


class LLMGateway(Protocol):
    """Contract shared by every model provider.

    Both the mock and the real provider return the same shape so the runtime
    parses them through one code path (`json.loads` + schema validation).
    """

    model: str

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]: ...


class GatewayResult(dict):
    """Typed alias for the gateway return contract.

    Keys: ``content`` (str), ``tool_calls`` (list of {name, arguments}),
    ``usage`` (dict[str, int]).
    """
