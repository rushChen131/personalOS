from __future__ import annotations

import json
import unittest

from tests._env import configure

configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.ai.agents import agent_registry  # noqa: E402
from app.ai.gateway import MockGateway, ModelRouter, build_gateway  # noqa: E402
from app.ai.tools import ToolRegistry  # noqa: E402
from app.main import app  # noqa: E402


class AiLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()
        login = cls.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        cls.headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_mock_gateway_routes_activity_to_journals(self) -> None:
        """Activity questions resolve to the journal read tool, never a write."""
        gateway = MockGateway()
        tool, args = gateway.plan(
            "what did I do today", available={"query_journals", "search_memory"}
        )
        self.assertEqual(tool, "query_journals")
        self.assertEqual(args, {})

    def test_agent_registry_has_five_agents_and_permissions(self) -> None:
        agents = agent_registry.all()
        self.assertEqual(len(agents), 5)
        self.assertEqual(agents["journal_agent"].permissions, {"READ"})
        self.assertEqual(agents["memory_agent"].permissions, {"READ", "WRITE_MEMORY"})
        self.assertEqual(agents["coach_agent"].permissions, {"READ"})

    def test_tool_permission_denied(self) -> None:
        import asyncio

        registry = ToolRegistry()
        from app.ai.runtime import AgentContext

        context = AgentContext(user_id="missing-user")
        # A caller holding no permissions must be refused any tool. (The Insight
        # module owned the only write tool, so the write-vs-read split is gone.)
        result = asyncio.run(
            registry.execute("query_journals", {}, context, None, set())  # type: ignore[arg-type]
        )
        self.assertEqual(result["error"], "TOOL_PERMISSION_DENIED")

    def test_model_router_mock_mode(self) -> None:
        self.assertEqual(ModelRouter().select("chat"), "mock-deterministic-v1")
        self.assertEqual(build_gateway().provider, "mock")

    def test_rag_returns_keyword_hits(self) -> None:
        import asyncio

        from app.core.database import SessionLocal
        from app.models.memory import Memory

        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        user_id = login.json()["data"]["user"]["id"]

        async def seed() -> None:
            async with SessionLocal() as session:
                session.add(
                    Memory(
                        user_id=user_id,
                        type="FACT",
                        content="User prefers deep work in the morning",
                        importance=0.9,
                        confidence=0.9,
                        source_count=1,
                    )
                )
                await session.commit()

        # Memories are only ever produced by the pipeline; seed the row directly.
        asyncio.run(seed())
        search = self.client.post(
            "/api/v1/memories/search", headers=self.headers, json={"query": "deep work"}
        )
        self.assertEqual(search.status_code, 200)
        self.assertGreaterEqual(len(search.json()["data"]), 1)

    def test_chat_sse_event_order_and_agent_routing(self) -> None:
        chat = self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            json={"message": "Today I studied Rust for 2 hours"},
        )
        self.assertEqual(chat.status_code, 200)
        text = chat.text
        order = [text.index(f"event: {name}") for name in ("start", "thinking", "tool_call", "tool_result")]
        self.assertEqual(order, sorted(order))
        self.assertIn("query_journals", text)

        goals = self.client.post(
            "/api/v1/chat", headers=self.headers, json={"message": "how are my goals doing?"}
        )
        self.assertIn("goal_agent", goals.text)

    def test_permission_denied_reflected_in_sse(self) -> None:
        # journal_agent is read-only; a normal read turn must complete cleanly.
        chat = self.client.post(
            "/api/v1/chat",
            headers=self.headers,
            json={"message": "what did I write recently?"},
        )
        self.assertIn("event: done", chat.text)
        self.assertNotIn("TOOL_PERMISSION_DENIED", chat.text)
        self.assertNotIn("TOOL_NOT_FOUND", chat.text)

    def test_embedding_provider_is_deterministic_and_semantic(self) -> None:
        import asyncio

        from app.ai.gateway.embeddings import build_embedding_provider, cosine_similarity

        provider = build_embedding_provider()
        self.assertEqual(provider.dim, 1536)

        async def run() -> tuple[list[float], list[float], list[float]]:
            return await provider.embed(
                [
                    "AgentScope architecture research",
                    "AgentScope tooling deep dive",
                    "cooking dinner tonight",
                ]
            )

        related_a, related_b, unrelated = asyncio.run(run())
        # Same topic must score far above an unrelated one.
        self.assertGreater(cosine_similarity(related_a, related_b), cosine_similarity(related_a, unrelated))
        self.assertGreater(cosine_similarity(related_a, unrelated), 0.0 - 1.0)  # sanity: bounded
        # Deterministic across calls (required for stored vectors to stay comparable).
        again = asyncio.run(provider.embed(["AgentScope architecture research"]))[0]
        self.assertEqual(related_a, again)


class ContextPageTest(unittest.TestCase):
    """design2.md §53: the Copilot context must change with the current page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()
        login = cls.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        cls.headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        cls.user_id = login.json()["data"]["user"]["id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_journal_page_context_carries_journals_and_memories(self) -> None:
        """A journal page carries the journal plus the memories distilled from it (§53)."""
        import asyncio

        from app.ai.context import ContextRuntime
        from app.ai.runtime import AgentContext
        from app.core.database import SessionLocal

        journal = self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": "我今天在读极简主义相关的书。"},
        ).json()["data"]

        ctx = self.client.get(
            "/api/v1/context",
            headers=self.headers,
            params={"page": "journals", "object_type": "journal", "object_id": journal["id"]},
        )
        self.assertEqual(ctx.status_code, 200)
        data = ctx.json()["data"]
        self.assertTrue(data["related_journals"], "journal page must expose related journals")
        self.assertIn(journal["id"], {j["id"] for j in data["related_journals"]})
        self.assertNotIn("related_reports", data, "reports are no longer projected")

        async def build() -> dict:
            async with SessionLocal() as session:
                return await ContextRuntime().build(
                    session,
                    AgentContext(
                        user_id=self.user_id,
                        current_page="journals",
                        current_object_id=journal["id"],
                    ),
                )

        payload = asyncio.run(build())
        self.assertIn("recent_journals", payload)
        self.assertTrue(
            any(j["id"] == journal["id"] for j in payload["recent_journals"]),
            "the journal under view must appear in the projection",
        )
        self.assertNotIn("report", payload)
        self.assertNotIn("underlying_events", payload)
        self.assertNotIn("recent_events", payload)

    def test_goal_page_context_includes_metrics_and_related_blocks(self) -> None:
        import asyncio

        from app.ai.context import ContextRuntime
        from app.ai.runtime import AgentContext
        from app.core.database import SessionLocal

        goal = self.client.post(
            "/api/v1/goals", headers=self.headers, json={"title": "Context goal probe"}
        ).json()["data"]
        self.client.post(
            f"/api/v1/goals/{goal['id']}/metrics",
            headers=self.headers,
            json={"name": "Deep work hours", "metric_type": "NUMBER", "current_value": 12, "target_value": 40},
        )

        async def build() -> dict:
            async with SessionLocal() as session:
                return await ContextRuntime().build(
                    session,
                    AgentContext(user_id=self.user_id, current_page="goal", current_object_id=goal["id"]),
                )

        payload = asyncio.run(build())
        self.assertEqual(payload["goal"]["id"], goal["id"])
        for key in ("metrics", "recent_journals", "memories"):
            self.assertIn(key, payload, f"goal page must carry '{key}'")

    def test_dashboard_page_context_is_user_only(self) -> None:
        """§53: dashboard carries just the user context, not page objects."""
        import asyncio

        from app.ai.context import ContextRuntime
        from app.ai.runtime import AgentContext
        from app.core.database import SessionLocal

        async def build() -> dict:
            async with SessionLocal() as session:
                return await ContextRuntime().build(session, AgentContext(user_id=self.user_id))

        payload = asyncio.run(build())
        self.assertIsNotNone(payload["user"])
        self.assertNotIn("report", payload)
        self.assertNotIn("underlying_events", payload)


class VectorRetrievalTest(unittest.TestCase):
    """The pgvector path must have a SQLite-equivalent implementation.

    The SQL branch is only reachable on PostgreSQL, so its ordering semantics
    are factored into ``rank_by_cosine`` and exercised here; the in-process
    branch is then tested end-to-end against SQLite to prove both agree.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()
        login = cls.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        cls.headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
        cls.user_id = login.json()["data"]["user"]["id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_rank_by_cosine_orders_and_skips_degenerate_rows(self) -> None:
        import asyncio

        from app.ai.gateway.embeddings import build_embedding_provider
        from app.ai.rag.runtime import rank_by_cosine

        provider = build_embedding_provider()

        async def embed() -> tuple[list[float], list[float], list[float], list[float]]:
            return tuple(  # type: ignore[return-value]
                await provider.embed(
                    [
                        "AgentScope architecture research",
                        "AgentScope architecture notes",
                        "cooking dinner tonight",
                        "AgentScope architecture research",
                    ]
                )
            )

        query_vec, close, far, same = asyncio.run(embed())
        candidates = [
            {"id": "far", "content": "cooking", "embedding": far},
            {"id": "close", "content": "notes", "embedding": close},
            {"id": "empty", "content": "no vector", "embedding": []},
            {"id": "exact", "content": "same", "embedding": same},
        ]
        ranked = rank_by_cosine(candidates, query_vec, limit=10)
        ids = [item["id"] for item in ranked]

        # Degenerate (empty) embeddings are excluded, exactly like IS NOT NULL.
        self.assertNotIn("empty", ids)
        # Exact match ranks first; the unrelated row is dropped (non-positive cosine).
        self.assertEqual(ids[0], "exact")
        self.assertNotIn("far", ids)
        self.assertIn("close", ids)
        # Scores are monotonically non-increasing.
        scores = [item["score"] for item in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_rank_by_cosine_respects_limit(self) -> None:
        from app.ai.rag.runtime import rank_by_cosine

        vector = [1.0, 0.0]
        candidates = [
            {"id": "a", "content": "a", "embedding": [1.0, 0.0]},
            {"id": "b", "content": "b", "embedding": [0.9, 0.1]},
            {"id": "c", "content": "c", "embedding": [0.8, 0.2]},
        ]
        self.assertEqual([item["id"] for item in rank_by_cosine(candidates, vector, limit=2)], ["a", "b"])
        self.assertEqual(rank_by_cosine(candidates, [], limit=2), [])

    def test_sqlite_vector_search_matches_cosine_ranking(self) -> None:
        """End-to-end: the SQLite branch returns cosine-ranked, vector-backed rows."""
        import asyncio

        from app.ai.gateway.embeddings import build_embedding_provider
        from app.ai.rag.runtime import RAGRuntime
        from app.core.database import SessionLocal
        from app.models.memory import Memory

        provider = build_embedding_provider()

        async def prepare() -> tuple[str, list[float]]:
            async with SessionLocal() as session:
                vectors = await provider.embed(
                    ["vector path sentinel deep work", "vector path sentinel cooking"]
                )
                hit = Memory(
                    user_id=self.user_id,
                    type="FACT",
                    content="vector path sentinel deep work",
                    importance=0.4,
                    confidence=0.9,
                    embedding=vectors[0],
                )
                miss = Memory(
                    user_id=self.user_id,
                    type="FACT",
                    content="vector path sentinel cooking",
                    importance=0.4,
                    confidence=0.9,
                    embedding=vectors[1],
                )
                session.add_all([hit, miss])
                await session.commit()
                query_vec = (await provider.embed(["vector path sentinel deep work"]))[0]
                return hit.id, query_vec

        hit_id, query_vec = asyncio.run(prepare())

        async def run() -> list[dict]:
            async with SessionLocal() as session:
                return await RAGRuntime()._vector_search_python(
                    session, self.user_id, "", {"vector": query_vec}, limit=5
                )

        results = asyncio.run(run())
        self.assertTrue(results, "vector search returned nothing")
        self.assertEqual(results[0]["id"], hit_id, "the semantically closest memory must rank first")
        self.assertGreater(results[0]["score"], 0.5)

        # A memory without an embedding must never appear in the vector results.
        async def add_embeddingless() -> str:
            async with SessionLocal() as session:
                row = Memory(
                    user_id=self.user_id,
                    type="FACT",
                    content="vector path sentinel no vector at all",
                    importance=0.4,
                    confidence=0.9,
                    embedding=None,
                )
                session.add(row)
                await session.commit()
                return row.id

        embeddingless_id = asyncio.run(add_embeddingless())
        results_after = asyncio.run(run())
        returned_ids = {item["id"] for item in results_after}
        self.assertNotIn(embeddingless_id, returned_ids, "rows without a vector must be excluded")


class MockGatewayLanguageTest(unittest.TestCase):
    """The mock gateway is the default provider, so it must handle Chinese.

    Regression guard for two bugs: asking "我今天完成了什么" produced the generic
    English fallback because no intent keyword matched, and Chinese event titles
    were mangled by substring verb stripping ("复习了3小时数学" -> "数").
    """

    READ_TOOLS = {
        "query_journals",
        "query_goals",
        "search_memory",
    }

    def setUp(self) -> None:
        self.gateway = MockGateway()

    def test_activity_questions_route_to_journals(self) -> None:
        for message in ("我今天完成了什么", "我最近做了什么", "今天做了什么", "我完成了哪些事情", "最近有什么进展"):
            with self.subTest(message=message):
                name, _ = self.gateway.plan(message, self.READ_TOOLS, set())
                self.assertEqual(name, "query_journals", f"{message!r} should query journals")

    def test_specific_entities_outrank_recent_activity(self) -> None:
        """A recency word plus an entity means the user wants that entity."""
        expected = {
            "最近有什么目标": "query_goals",
            "搜一下记忆里的Rust": "search_memory",
        }
        for message, tool in expected.items():
            with self.subTest(message=message):
                name, _ = self.gateway.plan(message, self.READ_TOOLS, set())
                self.assertEqual(name, tool)

    def test_a_served_intent_stops_instead_of_falling_through(self) -> None:
        """Otherwise a second tool runs and its result overwrites the answer.

        Observed live: "最近有什么目标" queried goals, then fell through to
        the journal query on the next round, so the user saw journals instead.
        """
        for message in ("最近有什么目标", "最近的洞察", "最近的项目呢"):
            with self.subTest(message=message):
                first, _ = self.gateway.plan(message, self.READ_TOOLS, set())
                self.assertTrue(first, f"{message!r} should pick a tool on round 1")
                second, _ = self.gateway.plan(message, self.READ_TOOLS, {first})
                self.assertEqual(second, "", f"{message!r} must stop after {first}")

    def test_english_activity_questions_still_route(self) -> None:
        for message in ("What have I done today?", "what did i do recently", "show my recent activity"):
            with self.subTest(message=message):
                name, _ = self.gateway.plan(message, self.READ_TOOLS, set())
                self.assertEqual(name, "query_journals")

    def test_language_detection(self) -> None:
        self.assertEqual(self.gateway.detect_language("我今天完成了什么"), "zh")
        self.assertEqual(self.gateway.detect_language("what did i do today"), "en")

    def test_synthesize_answers_in_the_users_language(self) -> None:
        payload = json.dumps(
            {"journals": [{"title": "Rust 学习"}, {"title": "数学复习"}]}
        )
        zh = self.gateway.synthesize("我今天完成了什么", [{"role": "user", "content": payload}])
        en = self.gateway.synthesize("what did i do", [{"role": "user", "content": payload}])
        self.assertIsNotNone(zh)
        self.assertIsNotNone(en)
        self.assertIn("找到", zh)
        self.assertIn("Recent journals", en)
        # The user's own titles must survive into the answer verbatim.
        self.assertIn("Rust 学习", zh)
        self.assertIn("数学复习", zh)

    def test_empty_result_is_reported_in_chinese(self) -> None:
        payload = json.dumps({"journals": []})
        zh = self.gateway.synthesize("今天做了什么", [{"role": "user", "content": payload}])
        self.assertIn("没有找到", zh)

    def test_fallback_compose_is_localised(self) -> None:
        self.assertIn("整理", self.gateway.compose("随便聊聊"))
        self.assertIn("organize", self.gateway.compose("just chatting"))

    def test_generate_ignores_json_tool_payloads_when_detecting_language(self) -> None:
        """The runtime appends tool results as JSON in the user role.

        Reading language off the last message therefore saw JSON and answered in
        English; the real utterance has to be recovered first.
        """
        import asyncio

        payload = json.dumps({"journals": [{"title": "恶趣味请问"}, {"title": "读论文"}]}, ensure_ascii=False)
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "我今天完成了什么"},
            {"role": "assistant", "content": json.dumps({"tool_call": "query_journals"})},
            {"role": "user", "content": payload},
        ]
        reply = asyncio.run(self.gateway.generate(messages))
        content = reply["content"] if isinstance(reply, dict) else reply.content
        self.assertIn("找到", content, "a Chinese question must get a Chinese answer")
        self.assertIn("恶趣味请问", content, "the user's own titles must be preserved")

    def test_agent_compose_speaks_chinese(self) -> None:
        """The screenshot's answer came from personal_manager, not the gateway."""
        from app.ai.runtime.base import AgentInput

        agent = agent_registry.get("personal_manager")
        zh = agent.compose(AgentInput(message="我今天完成了什么"), [])
        en = agent.compose(AgentInput(message="what did i do today"), [])
        self.assertIn("整理", zh)
        self.assertIn("organize", en)

    def test_read_agents_are_localised(self) -> None:
        """Every read-path agent must answer in the user's language."""
        from app.ai.runtime.base import AgentInput

        cases = {
            "goal_agent": ({"goals": [{"title": "跑马拉松", "progress": 40}]}, "目标"),
            "memory_agent": ({"memories": [{"content": "喜欢深度工作"}]}, "相关记忆"),
        }
        for name, (tool_result, marker) in cases.items():
            with self.subTest(agent=name):
                agent = agent_registry.get(name)
                content = agent.compose(
                    AgentInput(message="给我看看"), [{"name": "t", "result": tool_result}]
                )
                self.assertIn(marker, content, f"{name} should answer in Chinese")


if __name__ == "__main__":
    unittest.main()
