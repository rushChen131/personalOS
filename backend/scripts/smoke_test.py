"""End-to-end endpoint smoke test (plan item A2 / A4).

Runs the full API surface in-process against a throwaway SQLite database using
FastAPI's TestClient. Exercises auth, the journal/todo/memory CRUD
resources, the removal of the event/report/insight modules, and the chat
conversation lifecycle + SSE stream.

    cd backend && .venv/Scripts/python.exe scripts/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_DB = Path(tempfile.gettempdir()) / "personalos_smoke.db"
if _DB.exists():
    _DB.unlink()
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{_DB.as_posix()}",
        "LLM_PROVIDER": "mock",
        "SEED_DEMO_USER": "true",
        "SECRET_KEY": "smoke-secret",
        "FRONTEND_ORIGIN": "http://localhost:3000",
        # Settings read ``.env`` unconditionally, so without this the smoke run
        # would append its throwaway traffic to the real dev log file.
        "LOG_FILE": "",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

_passed: list[str] = []
_failed: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        _passed.append(label)
        print(f"  PASS  {label}")
    else:
        _failed.append(label)
        print(f"  FAIL  {label}  {detail}")


def data(response) -> object:
    body = response.json()
    assert body.get("success") is True, body
    assert "request_id" in body
    return body["data"]


def main() -> int:
    with TestClient(app) as client:
        print("\n[auth]")
        bootstrap = client.get("/api/v1/auth/bootstrap")
        check("GET /auth/bootstrap", bootstrap.status_code == 200, bootstrap.text)

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "demo@personalos.local", "password": "demo1234"},
        )
        check("POST /auth/login", login.status_code == 200, login.text)
        token = data(login)["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/v1/auth/me", headers=auth)
        check("GET /auth/me", me.status_code == 200 and data(me)["email"].startswith("demo@"))
        check(
            "GET /auth/me unauthorized -> 401",
            client.get("/api/v1/auth/me").status_code == 401,
        )

        print("\n[health]")
        health = client.get("/api/v1/health")
        check("GET /health", health.status_code == 200, health.text)

        print("\n[journals]")
        journal = client.post(
            "/api/v1/journals",
            headers=auth,
            json={
                "title": "Smoke",
                "content": "I studied Rust for 2 hours today.",
                "category": "LEARNING",
            },
        )
        check("POST /journals", journal.status_code in (200, 201), journal.text)
        journal_id = data(journal)["id"]
        check("POST /journals echoes category", data(journal)["category"] == "LEARNING", journal.text)
        check("GET /journals", client.get("/api/v1/journals", headers=auth).status_code == 200)
        check("GET /journals/{id}", client.get(f"/api/v1/journals/{journal_id}", headers=auth).status_code == 200)
        check(
            "GET /journals/{missing} -> 404",
            client.get("/api/v1/journals/nope", headers=auth).status_code == 404,
        )
        # Journals are the single authored input, so seed a few more: repeated
        # statements are what the memory engine promotes into a long-term fact.
        for entry in (
            "I have been writing my backend in Rust lately.",
            "Rust ownership finally clicked for me.",
            "Started a small Rust CLI to practice.",
        ):
            client.post("/api/v1/journals", headers=auth, json={"content": entry})

        # Category round-trip: the field must persist, echo, filter, and reject typos.
        investment = client.post(
            "/api/v1/journals",
            headers=auth,
            json={"content": "Rebalanced my index fund allocation.", "category": "INVESTMENT"},
        )
        check("POST /journals with category", investment.status_code in (200, 201), investment.text)
        check(
            "journal category echoed",
            data(investment)["category"] == "INVESTMENT",
            investment.text,
        )
        omitted = client.post("/api/v1/journals", headers=auth, json={"content": "No category supplied."})
        check(
            "journal category defaults to OTHER",
            data(omitted)["category"] == "OTHER",
            omitted.text,
        )
        by_category = client.get("/api/v1/journals?category=INVESTMENT", headers=auth)
        check("GET /journals?category=", by_category.status_code == 200, by_category.text)
        check(
            "GET /journals?category= filters",
            all(item["category"] == "INVESTMENT" for item in data(by_category)),
            by_category.text,
        )
        check(
            "GET /journals?category= excludes other categories",
            all(item["id"] != journal_id for item in data(by_category)),
            by_category.text,
        )
        bad_category = client.post(
            "/api/v1/journals",
            headers=auth,
            json={"content": "Typo category.", "category": "NOPE"},
        )
        check("POST /journals unknown category -> 422", bad_category.status_code == 422, bad_category.text)

        check("DELETE /journals/{id}", client.delete(f"/api/v1/journals/{journal_id}", headers=auth).status_code == 200)

        print("\n[todos]")
        todo = client.post(
            "/api/v1/todos",
            headers=auth,
            json={
                "title": "Learn Rust",
                "description": "Systems programming",
                "priority": 2,
                "category": "LEARNING",
            },
        )
        check("POST /todos", todo.status_code in (200, 201), todo.text)
        todo_id = data(todo)["id"]
        check("POST /todos echoes category", data(todo)["category"] == "LEARNING", todo.text)
        check("POST /todos starts open", data(todo)["completed_at"] is None, todo.text)
        check("GET /todos", client.get("/api/v1/todos", headers=auth).status_code == 200)
        check("GET /todos/{id}", client.get(f"/api/v1/todos/{todo_id}", headers=auth).status_code == 200)
        todos_by_category = client.get("/api/v1/todos?category=LEARNING", headers=auth)
        check("GET /todos?category=", todos_by_category.status_code == 200, todos_by_category.text)
        check(
            "GET /todos?category= filters",
            all(item["category"] == "LEARNING" for item in data(todos_by_category)),
            todos_by_category.text,
        )
        check(
            "GET /todos?category= excludes other categories",
            all(item["id"] != todo_id for item in data(client.get("/api/v1/todos?category=HEALTH", headers=auth))),
            todos_by_category.text,
        )
        # Completion is a timestamp: setting it is the check, clearing it reopens.
        done = client.put(f"/api/v1/todos/{todo_id}", headers=auth, json={"completed": True})
        check(
            "PUT /todos/{id} stamps completed_at",
            done.status_code == 200 and data(done)["completed_at"] is not None,
            done.text,
        )
        reopened = client.put(f"/api/v1/todos/{todo_id}", headers=auth, json={"completed": False})
        check(
            "PUT /todos/{id} clears completed_at",
            reopened.status_code == 200 and data(reopened)["completed_at"] is None,
            reopened.text,
        )
        check(
            "GET /todos?completed=false hides done items",
            all(
                item["completed_at"] is None
                for item in data(client.get("/api/v1/todos?completed=false", headers=auth))
            ),
            "completed filter",
        )
        bad_todo = client.post(
            "/api/v1/todos", headers=auth, json={"title": "Typo category", "category": "NOPE"}
        )
        check("POST /todos unknown category -> 422", bad_todo.status_code == 422, bad_todo.text)
        bad_filter = client.get("/api/v1/todos?category=NOPE", headers=auth)
        check(
            "GET /todos?category=<unknown> -> 422",
            bad_filter.status_code == 422,
            bad_filter.text,
        )
        metrics_gone = client.post(
            f"/api/v1/todos/{todo_id}/metrics",
            headers=auth,
            json={"name": "hours", "metric_type": "NUMBER", "target_value": 100},
        )
        check("POST /todos/{id}/metrics 404 (entry point removed)", metrics_gone.status_code == 404, metrics_gone.text)
        check("DELETE /todos/{id}", client.delete(f"/api/v1/todos/{todo_id}", headers=auth).status_code == 200)
        check(
            "GET /goals 404 (renamed to todos)",
            client.get("/api/v1/goals", headers=auth).status_code == 404,
        )

        print("\n[todo subtasks]")
        parent = client.post(
            "/api/v1/todos",
            headers=auth,
            json={"title": "Smoke parent", "category": "WORK", "target_date": "2026-11-30"},
        )
        check("POST /todos (parent)", parent.status_code == 200, parent.text)
        parent_id = data(parent)["id"]

        # The step is deliberately sent a conflicting category and date: the
        # parent's values must win, which is the whole point of title-only steps.
        step = client.post(
            "/api/v1/todos",
            headers=auth,
            json={
                "title": "Smoke step",
                "parent_id": parent_id,
                "category": "HEALTH",
                "target_date": "2030-01-01",
            },
        )
        check("POST /todos (step)", step.status_code == 200, step.text)
        step_id = data(step)["id"]
        check("step inherits category", data(step)["category"] == "WORK", step.text)
        check("step inherits target_date", data(step)["target_date"] == "2026-11-30", step.text)
        check("step carries parent_id", data(step)["parent_id"] == parent_id, step.text)
        check("step is a leaf", data(step)["children"] == [], step.text)

        grandchild = client.post(
            "/api/v1/todos", headers=auth, json={"title": "Smoke grandchild", "parent_id": step_id}
        )
        check("nesting deeper than one level -> 400", grandchild.status_code == 400, grandchild.text)
        orphan = client.post(
            "/api/v1/todos", headers=auth, json={"title": "Smoke orphan", "parent_id": "0" * 32}
        )
        check("unknown parent -> 404", orphan.status_code == 404, orphan.text)

        tree = data(client.get("/api/v1/todos", headers=auth))
        check("a step is never a top-level row", all(row["id"] != step_id for row in tree))
        node = next((row for row in tree if row["id"] == parent_id), None)
        check(
            "the parent carries its steps",
            node is not None and [child["id"] for child in node["children"]] == [step_id],
            str(node),
        )
        single = data(client.get(f"/api/v1/todos/{parent_id}", headers=auth))
        check("GET /todos/{id} includes children", [child["id"] for child in single["children"]] == [step_id])

        client.put(f"/api/v1/todos/{parent_id}", headers=auth, json={"completed": True})
        check(
            "ticking a parent leaves its step open",
            data(client.get(f"/api/v1/todos/{step_id}", headers=auth))["completed_at"] is None,
        )
        client.put(f"/api/v1/todos/{parent_id}", headers=auth, json={"completed": False})

        check(
            "DELETE /todos/{parent}",
            client.delete(f"/api/v1/todos/{parent_id}", headers=auth).status_code == 200,
        )
        # Foreign keys are off in SQLite, so this only holds because the
        # repository deletes the steps explicitly.
        check(
            "the step went with its parent",
            client.get(f"/api/v1/todos/{step_id}", headers=auth).status_code == 404,
        )

        print("\n[events + timeline + stats removed]")
        for method, path in (
            ("get", "/api/v1/events"),
            ("get", "/api/v1/events/timeline"),
            ("get", "/api/v1/events/stats"),
        ):
            response = getattr(client, method)(path, headers=auth)
            check(f"{method.upper()} {path} 404 (module removed)", response.status_code == 404, response.text)

        print("\n[projects removed]")
        removed = client.get("/api/v1/projects", headers=auth)
        check("GET /projects 404 (module removed)", removed.status_code == 404, removed.text)
        removed_post = client.post("/api/v1/projects", headers=auth, json={"name": "Rust Journey"})
        check("POST /projects 404 (module removed)", removed_post.status_code == 404, removed_post.text)

        print("\n[memories]")
        memories = client.get("/api/v1/memories", headers=auth)
        check("GET /memories", memories.status_code == 200, memories.text)
        memory_list = data(memories)
        if memory_list:
            check(
                "GET /memories/{id}",
                client.get(f"/api/v1/memories/{memory_list[0]['id']}", headers=auth).status_code == 200,
            )
        search = client.post("/api/v1/memories/search", headers=auth, json={"query": "Rust", "limit": 10})
        check("POST /memories/search", search.status_code == 200, search.text)
        scoped = client.post(
            "/api/v1/memories/search",
            headers=auth,
            json={"query": "Rust", "limit": 10, "category": "LEARNING"},
        )
        check("POST /memories/search with category", scoped.status_code == 200, scoped.text)
        # A category filter can only narrow the result set, never widen it.
        check(
            "POST /memories/search category narrows results",
            {item["id"] for item in data(scoped)} <= {item["id"] for item in data(search)},
            scoped.text,
        )
        check(
            "POST /memories/search category filters",
            all(item["category"] == "LEARNING" for item in data(scoped)),
            scoped.text,
        )
        memories_by_category = client.get("/api/v1/memories?category=LEARNING", headers=auth)
        check("GET /memories?category=", memories_by_category.status_code == 200, memories_by_category.text)
        check(
            "GET /memories?category= filters",
            all(item["category"] == "LEARNING" for item in data(memories_by_category)),
            memories_by_category.text,
        )
        # Manual entry point is gone: memories are distilled from journals only.
        manual = client.post(
            "/api/v1/memories",
            headers=auth,
            json={"type": "PREFERENCE", "content": "I prefer dark mode"},
        )
        check("POST /memories 405/404 (manual entry removed)", manual.status_code in (404, 405), manual.text)

        print("\n[reports]")
        # A quiet, fixed day keeps the aggregation deterministic.
        period = {"period_start": "2026-09-01", "period_end": "2026-09-01"}
        generated = client.post(
            "/api/v1/reports/generate", headers=auth, json={"type": "DAILY", **period}
        )
        check("POST /reports/generate", generated.status_code in (200, 201), generated.text)
        report = data(generated)
        report_id = report["id"]
        check("report carries a summary", bool(report["summary"]), generated.text)
        check("report content is structured", isinstance(report["content"], dict), generated.text)
        check("report content exposes journal_count", "journal_count" in report["content"], generated.text)
        check("report type echoed", report["type"] == "DAILY", generated.text)

        check("GET /reports", client.get("/api/v1/reports", headers=auth).status_code == 200)
        listed = data(client.get("/api/v1/reports?type=DAILY", headers=auth))
        check("GET /reports?type= filters", all(row["type"] == "DAILY" for row in listed), str(listed)[:200])
        check(
            "GET /reports/{id}",
            client.get(f"/api/v1/reports/{report_id}", headers=auth).status_code == 200,
        )

        # Idempotent: the same period must refresh in place, never duplicate.
        again = client.post("/api/v1/reports/generate", headers=auth, json={"type": "DAILY", **period})
        check("POST /reports/generate is idempotent", data(again)["id"] == report_id, again.text)

        # Scoping to one life domain must only count that domain.
        scoped = client.post(
            "/api/v1/reports/generate",
            headers=auth,
            json={"type": "DAILY", "dimension": "WORK", **period},
        )
        check("POST /reports/generate with dimension", scoped.status_code in (200, 201), scoped.text)
        check("scoped report records its dimension", data(scoped)["dimension"] == "WORK", scoped.text)
        check(
            "scoped report only counts that domain",
            set(data(scoped)["content"]["category_breakdown"]) <= {"WORK"},
            scoped.text,
        )

        check(
            "POST /reports/generate unknown type -> 422",
            client.post("/api/v1/reports/generate", headers=auth, json={"type": "NOPE"}).status_code == 422,
        )
        check(
            "GET /reports/{missing} -> 404",
            client.get("/api/v1/reports/nope", headers=auth).status_code == 404,
        )
        check(
            "DELETE /reports/{id}",
            client.delete(f"/api/v1/reports/{report_id}", headers=auth).status_code == 200,
        )

        print("\n[removed modules]")
        # Reports were rebuilt (see [reports] above), so Insight is the only
        # module still fully retired.
        insights = client.get("/api/v1/insights", headers=auth)
        check("GET /insights 404 (module removed)", insights.status_code == 404, insights.text)

        print("\n[chat]")
        conversation = client.post("/api/v1/chat/conversations", headers=auth)
        check("POST /chat/conversations", conversation.status_code in (200, 201), conversation.text)
        conversation_id = data(conversation)["id"]
        check("GET /chat/conversations", client.get("/api/v1/chat/conversations", headers=auth).status_code == 200)
        convo_detail = client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=auth)
        check("GET /chat/conversations/{id}", convo_detail.status_code == 200, convo_detail.text)

        stream = client.post(
            "/api/v1/chat",
            headers={**auth, "Accept": "text/event-stream"},
            json={"message": "What did I study today?", "context": {"type": "dashboard", "id": None}},
        )
        check("POST /chat returns event-stream", stream.status_code == 200, stream.text)
        text = stream.text
        check("SSE emits start", "event: start" in text, text[:300])
        check("SSE emits done", "event: done" in text, text[:300])

    print("\n" + "=" * 60)
    print(f"PASSED: {len(_passed)}   FAILED: {len(_failed)}")
    if _failed:
        print("Failures:")
        for item in _failed:
            print(f"  - {item}")
        return 1
    print("All endpoint checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
