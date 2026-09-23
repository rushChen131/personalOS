from __future__ import annotations

import json
import re
from typing import Any

from app.ai.gateway.base import GatewayResult


class MockGateway:
    """Deterministic rule-based provider used when no API key is configured.

    Produces the same ``{content, tool_calls, usage}`` contract as the real
    provider so the runtime never branches on the provider.
    """

    model = "mock-deterministic-v1"
    provider = "mock"

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> GatewayResult:
        # `messages` accumulates tool results as JSON blobs in the "user" role, so
        # the naive last-user-message is often serialized data rather than what
        # the person actually typed. Planning and language detection must use the
        # real utterance, otherwise Chinese questions get English answers.
        message = self._last_human_message(messages)
        available = {tool["function"]["name"] for tool in (tools or []) if "function" in tool}
        already_used = self._tools_already_used(messages)
        tool_name, arguments = self.plan(message, available, already_used)
        calls = [{"id": f"call_mock_{tool_name}", "name": tool_name, "arguments": arguments}] if tool_name else []
        if calls:
            content = ""
        else:
            content = self.synthesize(message, messages) or self.compose(message)
        return GatewayResult(
            content=content,
            tool_calls=calls,
            usage={"input_tokens": len(message.split()), "output_tokens": len(content.split())},
        )

    @staticmethod
    def _last_human_message(messages: list[dict[str, str]]) -> str:
        """The most recent user message that is prose, not a JSON tool payload."""
        for item in reversed(messages):
            if item.get("role") != "user":
                continue
            content = (item.get("content") or "").strip()
            if content.startswith("{"):
                try:
                    json.loads(content)
                except json.JSONDecodeError:
                    return content  # malformed JSON is still something they typed
                continue
            if content:
                return content
        # Everything was a tool payload (or the list was empty): fall back.
        return MockGateway._last_user_message(messages)

    def synthesize(self, message: str, messages: list[dict[str, str]]) -> str | None:
        """Produce a grounded final answer from the latest tool result, if any."""
        result = self._last_tool_result(messages)
        if result is None:
            return None
        zh = self.detect_language(message) == "zh"

        if "journals" in result:
            journals = result["journals"]
            if not journals:
                return "该时间段内没有找到日志。" if zh else "No journals found for that period."
            titles = [
                e.get("title") or (e.get("content") or "")[:24] for e in journals if e.get("title") or e.get("content")
            ]
            if zh:
                return f"找到 {len(titles)} 篇日志：" + "、".join(titles) + "。"
            return f"Recent journals: {', '.join(titles)}."
        if "memories" in result:
            memories = result["memories"]
            if not memories:
                return "没有匹配的记忆。" if zh else "No matching memories."
            joined = "；".join(m.get("content", "") for m in memories[:3]) + ("。" if zh else "")
            return ("相关记忆：" + joined) if zh else ("Relevant memories: " + joined + ".")
        if "goals" in result:
            goals = result["goals"]
            if not goals:
                return "没有找到目标。" if zh else "No goals found."
            items = "，".join(f"{g.get('title')}（{float(g.get('progress', 0)):.0f}%）" for g in goals)
            return ("目标：" + items + "。") if zh else ("Goals: " + items + ".")
        if "proposal" in result:
            return "该操作需要你确认后才会执行。" if zh else "This action needs your confirmation before I run it."
        return None

    @staticmethod
    def _last_tool_result(messages: list[dict[str, str]]) -> dict[str, Any] | None:
        for item in reversed(messages):
            if item.get("role") != "user":
                continue
            content = item.get("content", "")
            if content.startswith("{"):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return None

    @staticmethod
    def _tools_already_used(messages: list[dict[str, str]]) -> set[str]:
        """Detect prior tool invocations so the mock terminates instead of looping."""
        used: set[str] = set()
        for item in messages:
            if item.get("role") == "assistant" and '"tool_call"' in item.get("content", ""):
                match = re.search(r'"tool_call"\s*:\s*"([^"]+)"', item["content"])
                if match:
                    used.add(match.group(1))
        return used

    # -- planning rules -------------------------------------------------

    def plan(
        self, message: str, available: set[str] | None = None, already_used: set[str] | None = None
    ) -> tuple[str, dict[str, Any] | None]:
        """Return the (tool_name, arguments) the mock model wants to call."""
        normalized = message.lower()
        used = already_used or set()

        def allowed(name: str) -> bool:
            return (not available or name in available) and name not in used

        # Specific entity questions must outrank the catch-all "recent activity"
        # check: "最近有什么目标" mentions recency *and* goals, and the user wants
        # goals. Ordering these first is what keeps that distinction.
        #
        # Each branch is checked with `intent_allowed` rather than `allowed`: a
        # specific intent that has already been served should END the turn, not
        # fall through to the generic journal query and overwrite the answer.
        specific = (
            (("memory" in normalized or "记忆" in message), "search_memory",
             {"query": re.sub(r"[？?。.]", "", message)[-24:]}),
            (("goal" in normalized or "目标" in message), "query_goals", {}),
        )
        for matches, name, args in specific:
            if not matches:
                continue
            if (not available or name in available) and name not in used:
                return name, args
            # Already served or unavailable: the request was satisfied (or cannot
            # be), so terminate instead of calling an unrelated tool.
            return "", None

        if self._mentions_recent(normalized) and allowed("query_journals"):
            return "query_journals", {}

        return "", None

    @staticmethod
    def _last_user_message(messages: list[dict[str, str]]) -> str:
        for item in reversed(messages):
            if item.get("role") == "user":
                return item.get("content", "")
        return messages[-1].get("content", "") if messages else ""

    @staticmethod
    def _mentions_recent(normalized: str) -> bool:
        """Does the user want a look back over their activity?

        Kept deliberately broad: the mock is the default provider when no API key
        is configured, so an unrecognised phrasing silently degrades into the
        generic "I can help organize…" fallback instead of answering.
        """
        english = ("recent", "what am i", "what have i", "what did i", "today", "yesterday")
        chinese = (
            "最近",
            "今天",
            "昨天",
            "这周",
            "本周",
            "上周",
            "本月",
            "这个月",
            "完成",
            "做了",
            "干了",
            "进展",
            "记录",
        )
        return any(word in normalized for word in english) or any(word in normalized for word in chinese)

    @staticmethod
    def detect_language(text: str) -> str:
        """Return "zh" when the text is predominantly Chinese, else "en"."""
        han = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        # A handful of Han characters is enough to signal intent in mixed input.
        return "zh" if han >= 2 else "en"

    @staticmethod
    def compose(message: str) -> str:
        normalized = message.lower()
        zh = MockGateway.detect_language(message) == "zh"
        if any(word in normalized for word in ("hello", "hi ", "hey")) or message.startswith("你好"):
            return "你好！我可以帮你回顾日志、目标和记忆。" if zh else (
                "Hi! I can help you review journals, goals, and memories."
            )
        if any(word in normalized for word in ("help", "what can you")) or "能做什么" in message:
            if zh:
                return "我可以回顾你的日志、查看目标、搜索记忆。"
            return "I can review your journals, goals, and memories."
        if zh:
            return "我可以帮你整理日志、目标和记忆。你可以试试问「我最近写了什么」或「今天完成了什么」。"
        return "I can help organize your journals, goals, and memories."

    # -- structured output helpers (used by agents) ----------------------

    async def structured(self, messages: list[dict[str, str]], schema_hint: dict[str, Any]) -> dict[str, Any]:
        """Return a deterministic JSON object for agents that expect structure."""
        message = self._last_user_message(messages)
        return {"message": message}
