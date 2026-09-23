from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.runtime import RAGRuntime
from app.ai.runtime.base import (
    READ,
    AgentContext,
)
from app.ai.tools.proposals import action_proposals
from app.core.errors import ErrorCode


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    permission: str
    input_schema: dict[str, Any]
    requires_confirmation: bool = False
    task_type: str = "chat"


class ToolRegistry:
    """Owns every tool definition and enforces agent permissions on dispatch.

    Tools are deliberately journal-centric: journals are the only input the
    user authors directly, so "what have I been doing" is answered from
    journals and the memories distilled from them.
    """

    def __init__(self, rag: RAGRuntime | None = None) -> None:
        self.rag = rag or RAGRuntime()
        self.definitions: dict[str, ToolDefinition] = {
            "query_journals": ToolDefinition(
                "query_journals",
                "Search the user's recent journal entries",
                READ,
                {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}},
            ),
            "query_goals": ToolDefinition(
                "query_goals", "List goals with progress", READ, {"type": "object", "properties": {}}
            ),
            "search_memory": ToolDefinition(
                "search_memory",
                "Hybrid search across memories",
                READ,
                {"type": "object", "properties": {"query": {"type": "string"}}},
            ),
            "calendar_tool": ToolDefinition(
                "calendar_tool",
                "Placeholder for external calendar sync",
                READ,
                {"type": "object", "properties": {}},
            ),
        }

    def schema_for(self, names: list[str]) -> list[dict[str, Any]]:
        """OpenAI-style tool schema for the subset an agent may call."""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": self.definitions[name].description,
                    "parameters": self.definitions[name].input_schema,
                },
            }
            for name in names
            if name in self.definitions
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: AgentContext,
        session: AsyncSession,
        permissions: set[str],
    ) -> dict[str, Any]:
        definition = self.definitions.get(name)
        if definition is None:
            return {"error": ErrorCode.TOOL_NOT_FOUND.value, "tool": name}
        if definition.permission not in permissions:
            return {"error": ErrorCode.TOOL_PERMISSION_DENIED.value, "tool": name}
        if definition.requires_confirmation:
            return {
                "proposal": action_proposals.create(
                    context.user_id,
                    name,
                    arguments,
                    agent_name=(context.metadata or {}).get("agent_name"),
                    reason=f"'{name}' is a high-risk tool and requires confirmation.",
                )
            }

        started = time.perf_counter()
        handler = getattr(self, f"_run_{name}", None)
        if handler is None:
            return {"error": ErrorCode.TOOL_NOT_FOUND.value, "tool": name}
        result = await handler(session, context, arguments or {})
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    async def execute_approved(
        self,
        name: str,
        arguments: dict[str, Any],
        context: AgentContext,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Execute a tool the user has already explicitly confirmed (§67).

        This entry point deliberately skips the ``requires_confirmation``
        interception (the confirmation already happened) but still enforces
        that the tool exists and that the agent is permitted to call it, so a
        stale or forged proposal cannot escalate privileges.
        """
        definition = self.definitions.get(name)
        if definition is None:
            return {"error": ErrorCode.TOOL_NOT_FOUND.value, "tool": name}
        from app.ai.agents.base import agent_registry

        agent_name = (context.metadata or {}).get("agent_name")
        agent = agent_registry.get(agent_name) if agent_name else None
        if agent is not None and definition.permission not in agent.permissions:
            return {"error": ErrorCode.TOOL_PERMISSION_DENIED.value, "tool": name}
        handler = getattr(self, f"_run_{name}", None)
        if handler is None:
            return {"error": ErrorCode.TOOL_NOT_FOUND.value, "tool": name}
        started = time.perf_counter()
        result = await handler(session, context, arguments or {})
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        return result

    # -- read tools ------------------------------------------------------

    async def _run_query_journals(
        self, session: AsyncSession, context: AgentContext, args: dict[str, Any]
    ) -> dict[str, Any]:
        from sqlalchemy import select

        from app.models.journal import Journal

        limit = int(args.get("limit", 10))
        query = (args.get("query") or "").strip()
        stmt = select(Journal).where(Journal.user_id == context.user_id)
        if query:
            stmt = stmt.where(Journal.content.ilike(f"%{query}%"))
        stmt = stmt.order_by(Journal.created_at.desc()).limit(limit)
        rows = list((await session.scalars(stmt)).unique())
        return {
            "journals": [
                {"id": row.id, "title": row.title, "content": row.content} for row in rows
            ]
        }

    async def _run_query_goals(
        self, session: AsyncSession, context: AgentContext, args: dict[str, Any]
    ) -> dict[str, Any]:
        from sqlalchemy import select

        from app.models.project import Goal

        rows = list((await session.scalars(select(Goal).where(Goal.user_id == context.user_id).limit(20))).unique())
        return {
            "goals": [
                {
                    "id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "progress": float(row.progress),
                }
                for row in rows
            ]
        }

    async def _run_search_memory(
        self, session: AsyncSession, context: AgentContext, args: dict[str, Any]
    ) -> dict[str, Any]:
        hits = await self.rag.search(
            session, context.user_id, args.get("query", ""), filters={"kind": "memory"}, top_k=10
        )
        return {"memories": [h for h in hits if h["kind"] == "memory"]}

    async def _run_calendar_tool(
        self, session: AsyncSession, context: AgentContext, args: dict[str, Any]
    ) -> dict[str, Any]:
        return {"status": "not_configured", "message": "Calendar sync is not configured in local mode."}


__all__ = [
    "ToolDefinition",
    "ToolRegistry",
]
