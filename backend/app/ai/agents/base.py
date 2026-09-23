from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.ai.gateway.mock_gateway import MockGateway
from app.ai.runtime.base import (
    READ,
    WRITE_INSIGHT,
    WRITE_MEMORY,
    AgentInput,
)


class BaseAgent(ABC):
    """Declarative agent contract: identity, permissions, tools, prompt."""

    name: str = "base"
    description: str = ""
    system_prompt: str = ""
    task_type: str = "chat"
    tools: list[str] = []
    permissions: set[str] = {READ}

    def allowed_tools(self, registry: Any) -> list[str]:
        """Tools this agent may call, filtered by its permission set."""
        return [
            name
            for name in self.tools
            if name in registry.definitions and registry.definitions[name].permission in self.permissions
        ]

    @abstractmethod
    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        """Turn tool results into the final user-facing answer."""


class PersonalManagerAgent(BaseAgent):
    name = "personal_manager"
    description = "Cross-domain assistant; understands, decomposes, queries, and synthesizes."
    task_type = "chat"
    system_prompt = (
        "You are PersonalOS's personal manager. Understand the request, break it down, "
        "call the read-only tools you need, then answer concisely using only retrieved facts. "
        "Always reply in the same language the user wrote in."
    )
    tools = ["query_journals", "query_goals", "search_memory", "query_insights"]
    permissions = {READ}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        zh = MockGateway.detect_language(input_.message) == "zh"
        if not tool_results:
            if zh:
                return "我可以帮你整理日志、目标、记忆和洞察。你可以试试问「我最近写了什么」或「今天完成了什么」。"
            return "I can help organize your journals, goals, memories, and insights."
        parts: list[str] = []
        for item in tool_results:
            result = item.get("result", {})
            if "journals" in result:
                titles = [
                    e.get("title") or (e.get("content") or "")[:24]
                    for e in result["journals"]
                    if e.get("title") or e.get("content")
                ]
                if zh:
                    parts.append("最近日志：" + ("、".join(titles) if titles else "没有找到日志"))
                else:
                    parts.append("Recent journals: " + (", ".join(titles) if titles else "no journals found"))
            if "memories" in result:
                snippets = [m.get("content", "") for m in result["memories"]][:3]
                if zh:
                    parts.append("相关记忆：" + ("；".join(snippets) if snippets else "没有找到"))
                else:
                    parts.append("Relevant memories: " + ("; ".join(snippets) if snippets else "none found"))
            if "goals" in result:
                goals = [f"{g['title']} ({float(g.get('progress', 0)):.0f}%)" for g in result["goals"]]
                if zh:
                    parts.append("目标：" + ("，".join(goals) if goals else "无"))
                else:
                    parts.append("Goals: " + (", ".join(goals) if goals else "none"))
            if "insights" in result:
                count = len(result["insights"])
                parts.append(f"洞察 {count} 条" if zh else f"Insights found: {count}")
        if not parts:
            return "完成。" if zh else "Done."
        return "".join(parts) if zh else " ".join(parts)


class JournalAgent(BaseAgent):
    name = "journal_agent"
    description = "Answers questions about the user's journal entries."
    task_type = "chat"
    system_prompt = (
        "Answer questions about the user's journal entries using the retrieved "
        "journal text only; never invent entries."
    )
    tools = ["query_journals", "search_memory"]
    permissions = {READ}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        zh = MockGateway.detect_language(input_.message) == "zh"
        for item in tool_results:
            journals = item.get("result", {}).get("journals")
            if journals:
                if zh:
                    return f"找到 {len(journals)} 篇相关日志。"
                return f"Found {len(journals)} related journal entr{'y' if len(journals) == 1 else 'ies'}."
        return "没有找到相关日志。" if zh else "No related journal entries found."


class GoalAgent(BaseAgent):
    name = "goal_agent"
    description = "Tracks goal progress and metrics."
    task_type = "chat"
    system_prompt = "Report goal status and progress; never modify goals without confirmation."
    tools = ["query_goals", "query_journals"]
    permissions = {READ}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        zh = MockGateway.detect_language(input_.message) == "zh"
        for item in tool_results:
            goals = item.get("result", {}).get("goals")
            if goals:
                items = [f"{g['title']}（{float(g.get('progress', 0)):.0f}%）" for g in goals]
                return ("目标：" + "，".join(items) + "。") if zh else (
                    "Goals: " + ", ".join(f"{g['title']} ({float(g.get('progress', 0)):.0f}%)" for g in goals)
                )
        return "没有找到目标。" if zh else "No goals found."


class MemoryAgent(BaseAgent):
    name = "memory_agent"
    description = "Searches and surfaces long-term memories."
    task_type = "memory_refine"
    system_prompt = "Answer using stored memories; cite the memory content you relied on."
    tools = ["search_memory", "query_journals"]
    permissions = {READ, WRITE_MEMORY}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        zh = MockGateway.detect_language(input_.message) == "zh"
        for item in tool_results:
            memories = item.get("result", {}).get("memories")
            if memories:
                joined = "；".join(m.get("content", "") for m in memories[:3])
                return ("相关记忆：" + joined + "。") if zh else ("Relevant memories: " + joined)
        return "没有匹配的记忆。" if zh else "No matching memories."


class InsightAgent(BaseAgent):
    name = "insight_agent"
    description = "Detects patterns and records insights."
    task_type = "insight"
    system_prompt = "Detect behavioural patterns from the provided data and record at most one insight."
    # `query_insights` is required so the agent can also *list* existing insights;
    # without it, "最近的洞察" routed here but had no way to read them.
    tools = ["query_insights", "query_journals", "query_goals", "search_memory", "create_insight"]
    permissions = {READ, WRITE_INSIGHT}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        zh = MockGateway.detect_language(input_.message) == "zh"
        for item in tool_results:
            result = item.get("result", {})
            insight = result.get("insight")
            if insight:
                return f"已记录洞察：{insight['title']}" if zh else f"Recorded insight: {insight['title']}"
            if "insights" in result:
                rows = result["insights"]
                if not rows:
                    return "没有找到洞察。" if zh else "No insights found."
                titles = [row.get("title", "") for row in rows if row.get("title")]
                if zh:
                    return f"找到 {len(rows)} 条洞察：" + "、".join(titles) + "。"
                return f"Found {len(rows)} insight(s): " + ", ".join(titles) + "."
        return "未发现值得记录的洞察。" if zh else "No actionable insight detected."


class CoachAgent(BaseAgent):
    name = "coach_agent"
    description = "Read-only coach; offers suggestions, never decides."
    task_type = "coach"
    system_prompt = "Offer at most three concrete, optional suggestions. Never take action."
    tools = ["query_journals", "query_goals", "search_memory"]
    permissions = {READ}

    def compose(self, input_: AgentInput, tool_results: list[dict[str, Any]]) -> str:
        return "Suggestion: protect a recurring focus block for your current priority."


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {
            agent.name: agent
            for agent in (
                PersonalManagerAgent(),
                JournalAgent(),
                GoalAgent(),
                MemoryAgent(),
                InsightAgent(),
                CoachAgent(),
            )
        }

    def get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def all(self) -> dict[str, BaseAgent]:
        return dict(self._agents)


agent_registry = AgentRegistry()

__all__ = [
    "AgentRegistry",
    "BaseAgent",
    "CoachAgent",
    "GoalAgent",
    "InsightAgent",
    "JournalAgent",
    "MemoryAgent",
    "PersonalManagerAgent",
    "agent_registry",
]
