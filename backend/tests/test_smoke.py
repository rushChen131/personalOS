from __future__ import annotations

import sqlite3
import unittest

from tests._env import configure

_db_file = configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.ai.tools import action_proposals  # noqa: E402
from app.main import app  # noqa: E402


class ApiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.__exit__(None, None, None)

    def test_core_api_flow(self) -> None:
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        self.assertEqual(login.status_code, 200)
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        self.assertEqual(self.client.get("/api/v1/auth/me", headers=headers).status_code, 200)

        journal = self.client.post(
            "/api/v1/journals", headers=headers, json={"title": "Smoke journal", "content": "Journal body"}
        )
        self.assertEqual(journal.status_code, 200)
        journal_id = journal.json()["data"]["id"]
        self.assertEqual(self.client.get("/api/v1/journals", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/journals/{journal_id}", headers=headers).status_code, 200)

        # Projects were removed from the API surface; the route must 404.
        self.assertEqual(self.client.get("/api/v1/projects", headers=headers).status_code, 404)

        goal = self.client.post("/api/v1/goals", headers=headers, json={"title": "Smoke goal"})
        self.assertEqual(goal.status_code, 200)
        goal_id = goal.json()["data"]["id"]
        self.assertEqual(self.client.get("/api/v1/goals", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/goals/{goal_id}", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.put(f"/api/v1/goals/{goal_id}", headers=headers, json={"priority": 2}).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/goals/{goal_id}/metrics",
                headers=headers,
                json={"name": "Completion", "metric_type": "PERCENT", "current_value": 20, "target_value": 100},
            ).status_code,
            200,
        )

        # Journals are the only user-facing input; events/reports are gone.
        memory = self.client.post(
            "/api/v1/journals",
            headers=headers,
            json={"content": "我在用 searchable 这个词做冒烟测试，顺便记录一下今天的进展。"},
        )
        self.assertEqual(memory.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/journals", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/memories", headers=headers).status_code, 200)
        search = self.client.post("/api/v1/memories/search", headers=headers, json={"query": "searchable"})
        self.assertEqual(search.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/insights", headers=headers).status_code, 200)

        conversation = self.client.post(
            "/api/v1/chat/conversations", headers=headers, params={"title": "Smoke conversation"}
        )
        self.assertEqual(conversation.status_code, 200)
        conversation_id = conversation.json()["data"]["id"]
        self.assertEqual(self.client.get("/api/v1/chat/conversations", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers).status_code,
            200,
        )
        chat = self.client.post(
            "/api/v1/chat",
            headers=headers,
            json={"message": "Today I researched AgentScope for 3 hours"},
        )
        self.assertEqual(chat.status_code, 200)
        self.assertEqual(chat.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: start", chat.text)
        self.assertIn("event: tool_call", chat.text)
        self.assertIn("event: content", chat.text)
        self.assertIn("event: done", chat.text)
        recent = self.client.post(
            "/api/v1/chat", headers=headers, json={"message": "What have I done recently?"}
        )
        self.assertEqual(recent.status_code, 200)
        self.assertIn("query_journals", recent.text)
        database = sqlite3.connect(_db_file)
        try:
            self.assertGreaterEqual(database.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0], 2)
            self.assertGreaterEqual(database.execute("SELECT COUNT(*) FROM tool_runs").fetchone()[0], 2)
        finally:
            database.close()
        proposal = action_proposals.create(
            login.json()["data"]["user"]["id"],
            "create_insight",
            {"title": "Smoke insight", "content": "confirmed via proposal"},
            agent_name="insight_agent",
            reason="high-risk tool",
        )
        confirmation = self.client.post(f"/api/v1/actions/{proposal['id']}/confirm", headers=headers)
        self.assertEqual(confirmation.status_code, 200)
        confirmed = confirmation.json()["data"]
        # §67: confirming a proposal must actually execute the frozen call.
        self.assertEqual(confirmed["status"], "EXECUTED")
        self.assertEqual(confirmed["tool"], "create_insight")
        self.assertNotIn("error", confirmed)
        self.assertEqual(self.client.delete(f"/api/v1/journals/{journal_id}", headers=headers).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/goals/{goal_id}", headers=headers).status_code, 200)
