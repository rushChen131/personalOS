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

    def test_category_round_trip(self) -> None:
        """`category` is accepted, echoed back, filterable and validated."""
        login = self.client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

        created = self.client.post(
            "/api/v1/journals",
            headers=headers,
            json={"title": "Category journal", "content": "Journal body", "category": "INVESTMENT"},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["data"]["category"], "INVESTMENT")
        journal_id = created.json()["data"]["id"]

        # Omitting the field must fall back to OTHER rather than fail, so older
        # clients keep working.
        defaulted = self.client.post(
            "/api/v1/journals", headers=headers, json={"content": "No category given"}
        )
        self.assertEqual(defaulted.json()["data"]["category"], "OTHER")

        filtered = self.client.get(
            "/api/v1/journals", headers=headers, params={"category": "INVESTMENT"}
        )
        self.assertEqual(filtered.status_code, 200)
        rows = filtered.json()["data"]
        self.assertIn(journal_id, [row["id"] for row in rows])
        self.assertTrue(all(row["category"] == "INVESTMENT" for row in rows))

        # An unknown domain is rejected rather than written through.
        rejected = self.client.post(
            "/api/v1/journals",
            headers=headers,
            json={"content": "bad category", "category": "CRYPTO"},
        )
        self.assertEqual(rejected.status_code, 422)

        todo = self.client.post(
            "/api/v1/todos", headers=headers, json={"title": "Category todo", "category": "HEALTH"}
        )
        self.assertEqual(todo.json()["data"]["category"], "HEALTH")
        todo_id = todo.json()["data"]["id"]
        updated = self.client.put(
            f"/api/v1/todos/{todo_id}", headers=headers, json={"category": "LEARNING"}
        )
        self.assertEqual(updated.json()["data"]["category"], "LEARNING")

        # Memories are derived, so only the shape of the field is asserted here;
        # inheritance from source journals is covered in test_jobs_layer.py.
        memories = self.client.get("/api/v1/memories", headers=headers)
        self.assertEqual(memories.status_code, 200)
        self.assertTrue(all("category" in row for row in memories.json()["data"]))

        self.client.delete(f"/api/v1/journals/{journal_id}", headers=headers)
        self.client.delete(f"/api/v1/todos/{todo_id}", headers=headers)

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
        # Goals were renamed to todos; the old route must 404 too.
        self.assertEqual(self.client.get("/api/v1/goals", headers=headers).status_code, 404)

        todo = self.client.post("/api/v1/todos", headers=headers, json={"title": "Smoke todo"})
        self.assertEqual(todo.status_code, 200)
        todo_id = todo.json()["data"]["id"]
        self.assertEqual(self.client.get("/api/v1/todos", headers=headers).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/todos/{todo_id}", headers=headers).status_code, 200)
        self.assertEqual(
            self.client.put(f"/api/v1/todos/{todo_id}", headers=headers, json={"priority": 2}).status_code,
            200,
        )
        # Completion is a timestamp, not a status + progress pair.
        done = self.client.put(f"/api/v1/todos/{todo_id}", headers=headers, json={"completed": True})
        self.assertEqual(done.status_code, 200)
        self.assertIsNotNone(done.json()["data"]["completed_at"])
        reopened = self.client.put(f"/api/v1/todos/{todo_id}", headers=headers, json={"completed": False})
        self.assertEqual(reopened.status_code, 200)
        self.assertIsNone(reopened.json()["data"]["completed_at"])
        # The metrics entry point went with the progress bar.
        self.assertEqual(
            self.client.post(
                f"/api/v1/todos/{todo_id}/metrics",
                headers=headers,
                json={"name": "Completion", "metric_type": "PERCENT", "current_value": 20, "target_value": 100},
            ).status_code,
            404,
        )
        # A typo'd filter must fail loudly, not read as "you have no todos".
        self.assertEqual(self.client.get("/api/v1/todos?category=NOPE", headers=headers).status_code, 422)
        self.assertEqual(
            self.client.get("/api/v1/todos?completed=false", headers=headers).status_code, 200
        )
        self.assertEqual(self.client.get("/api/v1/todos?completed=NOPE", headers=headers).status_code, 422)

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
        # §67: confirming a proposal must actually execute the frozen call.
        # The flow is exercised with a surviving read tool, because the Insight
        # module (which owned the only write tool) has been retired.
        proposal = action_proposals.create(
            login.json()["data"]["user"]["id"],
            "query_journals",
            {"limit": 3},
            agent_name="journal_agent",
            reason="proposal confirmation smoke test",
        )
        confirmation = self.client.post(f"/api/v1/actions/{proposal['id']}/confirm", headers=headers)
        self.assertEqual(confirmation.status_code, 200)
        confirmed = confirmation.json()["data"]
        self.assertEqual(confirmed["status"], "EXECUTED")
        self.assertEqual(confirmed["tool"], "query_journals")
        self.assertNotIn("error", confirmed)
        self.assertEqual(self.client.delete(f"/api/v1/journals/{journal_id}", headers=headers).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/todos/{todo_id}", headers=headers).status_code, 200)


class NestedTodoTest(unittest.TestCase):
    """One level of nesting: a todo may own steps.

    The cascade in AC6 is asserted against SQLite directly, because the backend
    never issues ``PRAGMA foreign_keys=ON`` — the column's ``ondelete="CASCADE"``
    is inert here, so "the steps are gone" has to be proved by looking at rows
    rather than by trusting the constraint.
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

    @staticmethod
    def _row_id(api_id: str) -> str:
        """Translate an API id into its on-disk form.

        ``UUIDType`` stores a 32-char dashless hex on SQLite but the API hands
        back the dashed UUID, so a raw ``WHERE id = ?`` with the API value
        matches nothing — which would make the assertions below pass vacuously.
        """
        return api_id.replace("-", "")

    def _create(self, **body) -> dict:
        response = self.client.post("/api/v1/todos", headers=self.headers, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        todo = response.json()["data"]
        # Clean up even when a later assertion fails: every test module shares
        # one database file, so a leftover row would leak into other suites.
        self.addCleanup(
            lambda tid=todo["id"]: self.client.delete(
                f"/api/v1/todos/{tid}", headers=self.headers
            )
        )
        return todo

    def test_a_step_inherits_category_and_target_date(self) -> None:
        """AC1 — the parent wins even when the step is sent its own values."""
        parent = self._create(title="Nest parent A", category="WORK", target_date="2026-11-01")
        step = self._create(
            title="Nest step A",
            parent_id=parent["id"],
            category="HEALTH",
            target_date="2030-01-01",
        )
        self.assertEqual(step["parent_id"], parent["id"])
        self.assertEqual(step["category"], "WORK")
        self.assertEqual(step["target_date"], "2026-11-01")
        # A step is a leaf: it never carries steps of its own.
        self.assertEqual(step["children"], [])

    def test_depth_is_capped_at_one_level(self) -> None:
        """AC2 — a step cannot own steps."""
        parent = self._create(title="Nest parent B")
        step = self._create(title="Nest step B", parent_id=parent["id"])
        response = self.client.post(
            "/api/v1/todos",
            headers=self.headers,
            json={"title": "Nest grandchild B", "parent_id": step["id"]},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_unknown_and_foreign_parents_are_404(self) -> None:
        """AC3 — another user's todo must be indistinguishable from a missing one."""
        missing = self.client.post(
            "/api/v1/todos",
            headers=self.headers,
            json={"title": "Nest orphan", "parent_id": "0" * 32},
        )
        self.assertEqual(missing.status_code, 404, missing.text)

        foreign = self._create(title="Nest not yours")
        database = sqlite3.connect(_db_file)
        try:
            database.execute(
                "UPDATE todos SET user_id = ? WHERE id = ?",
                ("someone-else", self._row_id(foreign["id"])),
            )
            database.commit()
        finally:
            database.close()
        try:
            response = self.client.post(
                "/api/v1/todos",
                headers=self.headers,
                json={"title": "Nest orphan 2", "parent_id": foreign["id"]},
            )
            self.assertEqual(response.status_code, 404, response.text)
        finally:
            # Hand the row back so the shared database keeps a single owner.
            database = sqlite3.connect(_db_file)
            try:
                database.execute(
                    "UPDATE todos SET user_id = ? WHERE id = ?",
                    (self._row_id(self.user_id), self._row_id(foreign["id"])),
                )
                database.commit()
            finally:
                database.close()

    def test_children_only_appear_under_their_parent(self) -> None:
        """AC4 — a step is never a row of its own, on the list or the detail read."""
        parent = self._create(title="Nest parent C", category="LEARNING", target_date="2026-12-01")
        step = self._create(title="Nest step C1", parent_id=parent["id"])

        rows = self.client.get("/api/v1/todos", headers=self.headers).json()["data"]
        self.assertNotIn(step["id"], [row["id"] for row in rows])
        node = next(row for row in rows if row["id"] == parent["id"])
        self.assertEqual([child["id"] for child in node["children"]], [step["id"]])

        one = self.client.get(f"/api/v1/todos/{parent['id']}", headers=self.headers).json()["data"]
        self.assertEqual([child["id"] for child in one["children"]], [step["id"]])

    def test_completion_is_independent_across_the_edge(self) -> None:
        """AC5 — the parent's tick is the parent's alone, in both directions."""
        parent = self._create(title="Nest parent D")
        step = self._create(title="Nest step D1", parent_id=parent["id"])

        self.client.put(
            f"/api/v1/todos/{parent['id']}", headers=self.headers, json={"completed": True}
        )
        child_after = self.client.get(f"/api/v1/todos/{step['id']}", headers=self.headers).json()["data"]
        self.assertIsNone(child_after["completed_at"], "ticking a parent must not tick its steps")

        self.client.put(
            f"/api/v1/todos/{step['id']}", headers=self.headers, json={"completed": True}
        )
        parent_after = self.client.get(
            f"/api/v1/todos/{parent['id']}", headers=self.headers
        ).json()["data"]
        self.assertIsNotNone(parent_after["completed_at"], "ticking a step must not untick its parent")

    def test_deleting_a_parent_takes_its_steps(self) -> None:
        """AC6 — no row is left behind holding a dangling `parent_id`."""
        parent = self._create(title="Nest parent E")
        first = self._create(title="Nest step E1", parent_id=parent["id"])
        second = self._create(title="Nest step E2", parent_id=parent["id"])

        deleted = self.client.delete(f"/api/v1/todos/{parent['id']}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)

        database = sqlite3.connect(_db_file)
        try:
            # Documents *why* the cascade has to live in the repository: a fresh
            # connection defaults to foreign keys off, which is how the app runs.
            self.assertEqual(database.execute("PRAGMA foreign_keys").fetchone()[0], 0)
            dangling = database.execute(
                "SELECT COUNT(*) FROM todos WHERE parent_id = ?",
                (self._row_id(parent["id"]),),
            ).fetchone()[0]
            survivors = database.execute(
                "SELECT COUNT(*) FROM todos WHERE id IN (?, ?)",
                (self._row_id(first["id"]), self._row_id(second["id"])),
            ).fetchone()[0]
        finally:
            database.close()
        self.assertEqual(dangling, 0, "a step was left with a dangling parent_id")
        self.assertEqual(survivors, 0, "a step outlived its parent")

    def test_filters_apply_to_the_parent_row(self) -> None:
        """AC7 — a step never promotes itself into the top-level list."""
        parent = self._create(title="Nest parent F", category="WORK")
        step = self._create(title="Nest step F1", parent_id=parent["id"])

        open_rows = self.client.get("/api/v1/todos?completed=false", headers=self.headers).json()["data"]
        self.assertIn(parent["id"], [row["id"] for row in open_rows])
        self.assertNotIn(step["id"], [row["id"] for row in open_rows])

        # A step inherits the parent's category, so it must not surface as a
        # WORK row of its own when the filter is applied.
        work_rows = self.client.get("/api/v1/todos?category=WORK", headers=self.headers).json()["data"]
        self.assertIn(parent["id"], [row["id"] for row in work_rows])
        self.assertNotIn(step["id"], [row["id"] for row in work_rows])

        self.client.put(
            f"/api/v1/todos/{parent['id']}", headers=self.headers, json={"completed": True}
        )
        open_rows = self.client.get("/api/v1/todos?completed=false", headers=self.headers).json()["data"]
        self.assertNotIn(parent["id"], [row["id"] for row in open_rows])
        # Steps keep their own state, so a finished parent still carries them.
        done_rows = self.client.get("/api/v1/todos?completed=true", headers=self.headers).json()["data"]
        node = next(row for row in done_rows if row["id"] == parent["id"])
        self.assertEqual([child["id"] for child in node["children"]], [step["id"]])

    def test_a_step_cannot_edit_its_inherited_fields(self) -> None:
        """The write path enforces the same inheritance rule as the read path."""
        parent = self._create(title="Nest parent G", category="HEALTH", target_date="2026-12-15")
        step = self._create(title="Nest step G1", parent_id=parent["id"])

        self.client.put(
            f"/api/v1/todos/{step['id']}",
            headers=self.headers,
            json={"category": "WORK", "target_date": "2031-01-01"},
        )
        after = self.client.get(f"/api/v1/todos/{step['id']}", headers=self.headers).json()["data"]
        self.assertEqual(after["category"], "HEALTH")
        self.assertEqual(after["target_date"], "2026-12-15")
        # A title is still the step's own to change.
        self.client.put(
            f"/api/v1/todos/{step['id']}", headers=self.headers, json={"title": "Nest step G1 renamed"}
        )
        renamed = self.client.get(f"/api/v1/todos/{step['id']}", headers=self.headers).json()["data"]
        self.assertEqual(renamed["title"], "Nest step G1 renamed")

