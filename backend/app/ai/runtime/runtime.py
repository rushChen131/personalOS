from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agents.base import AgentRegistry, BaseAgent, agent_registry
from app.ai.context import ContextRuntime
from app.ai.gateway.base import LLMGateway
from app.ai.gateway.openai_gateway import build_gateway
from app.ai.runtime.base import AgentContext, AgentInput, AgentResult
from app.ai.tools.proposals import ActionProposalStore, action_proposals
from app.ai.tools.registry import ToolRegistry
from app.core.errors import ErrorCode
from app.core.logging import logger
from app.models.conversation import AgentRun, ToolRun

MAX_TOOL_ROUNDS = 3


class AgentRuntime:
    """Runs an agent through a bounded tool loop and records the full trace.

    Works identically with the mock and OpenAI gateways: the gateway proposes
    tool calls, the registry enforces permissions and executes them, and the
    agent composes the final answer.
    """

    def __init__(
        self,
        tools: ToolRegistry | None = None,
        gateway: LLMGateway | None = None,
        registry: AgentRegistry | None = None,
        proposals: ActionProposalStore | None = None,
    ) -> None:
        self.tools = tools or ToolRegistry()
        self.gateway = gateway or build_gateway()
        self.registry = registry or agent_registry
        self.proposals = proposals or action_proposals

    async def run(
        self,
        agent_name: str,
        context: AgentContext,
        input_: AgentInput,
        session: AsyncSession,
        emit: Any = None,
    ) -> AgentResult:
        agent = self.registry.get(agent_name) or self.registry.get("personal_manager")
        assert agent is not None
        if agent is None:  # pragma: no cover - defensive
            return AgentResult(False, "Agent not found")

        started = time.perf_counter()
        runtime_context = await ContextRuntime().build(session, context)
        run = AgentRun(
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            agent_name=agent.name,
            model=self.gateway.model,
            input={"message": input_.message, "variables": input_.variables, "context": runtime_context},
            status="RUNNING",
        )
        session.add(run)
        await session.flush()

        allowed = agent.allowed_tools(self.tools)
        tool_schemas = self.tools.schema_for(allowed)
        messages = self._build_messages(agent, runtime_context, input_)
        calls: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        content = ""
        status = "COMPLETED"
        error_message: str | None = None

        try:
            for round_index in range(MAX_TOOL_ROUNDS):
                if emit is not None and round_index == 0:
                    await emit("thinking", {"agent": agent.name})
                reply = await self.gateway.generate(messages, tools=tool_schemas or None)
                for key, value in (reply.get("usage") or {}).items():
                    usage[key] = usage.get(key, 0) + int(value)
                proposed = reply.get("tool_calls") or []
                if not proposed:
                    content = reply.get("content") or ""
                    break
                for call in proposed:
                    name = call.get("name", "")
                    arguments = call.get("arguments") or {}
                    if name not in allowed:
                        logger.warning("agent.tool.not_allowed", agent=agent.name, tool=name)
                        calls.append(
                            {
                                "name": name,
                                "arguments": arguments,
                                "result": {"error": ErrorCode.TOOL_PERMISSION_DENIED.value, "tool": name},
                            }
                        )
                        continue
                    if emit is not None:
                        await emit("tool_call", {"name": name, "arguments": arguments})
                    tool_run = ToolRun(
                        agent_run_id=run.id, tool_name=name, input=arguments, status="RUNNING"
                    )
                    session.add(tool_run)
                    await session.flush()
                    tool_started = time.perf_counter()
                    result = await self.tools.execute(
                        name, arguments, context, session, agent.permissions
                    )
                    result = json_safe(result)
                    tool_run.output = result
                    tool_run.status = "FAILED" if "error" in result else "COMPLETED"
                    tool_run.latency_ms = int((time.perf_counter() - tool_started) * 1000)
                    calls.append({"name": name, "arguments": arguments, "result": result})
                    if emit is not None:
                        await emit("tool_result", {"name": name, "result": result})
                    messages.append({"role": "assistant", "content": json.dumps({"tool_call": name})})
                    messages.append({"role": "user", "content": json.dumps(result, default=str)})
            if not content:
                content = agent.compose(input_, calls)
        except Exception as exc:  # pragma: no cover - provider dependent
            status = "FAILED"
            error_message = str(exc)
            content = agent.compose(input_, calls)
            logger.error("agent.run.failed", agent=agent.name, error=str(exc))

        run.output = json_safe({"content": content, "tool_calls": calls, "usage": usage})
        run.status = status
        run.error_message = error_message
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        run.input_tokens = usage.get("input_tokens", len(input_.message.split()))
        run.output_tokens = usage.get("output_tokens", len(content.split()))
        await session.flush()

        return AgentResult(
            success=status == "COMPLETED",
            content=content,
            structured_output={"tool_results": calls},
            tool_calls=calls,
            usage={"input_tokens": run.input_tokens or 0, "output_tokens": run.output_tokens or 0},
            metadata={"context": runtime_context, "agent": agent.name, "run_id": run.id},
        )

    @staticmethod
    def _build_messages(agent: BaseAgent, runtime_context: dict[str, Any], input_: AgentInput) -> list[dict[str, str]]:
        context_block = json.dumps(runtime_context, ensure_ascii=False, default=str)
        return [
            {"role": "system", "content": agent.system_prompt},
            {"role": "system", "content": f"User context: {context_block}"},
            {"role": "user", "content": input_.message},
        ]


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n".encode()


def json_safe(value: Any) -> Any:
    """Recursively coerce a value into something JSONB can persist."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


__all__ = ["AgentRuntime", "MAX_TOOL_ROUNDS", "json_safe", "sse"]
