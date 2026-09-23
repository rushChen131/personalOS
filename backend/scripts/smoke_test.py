"""End-to-end endpoint smoke test (plan item A2 / A4).

Runs the full API surface in-process against a throwaway SQLite database using
FastAPI's TestClient. Exercises auth, the journal/goal/memory/insight CRUD
resources, the removal of the event/report/timeline modules, and the chat
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
            json={"title": "Smoke", "content": "I studied Rust for 2 hours today."},
        )
        check("POST /journals", journal.status_code in (200, 201), journal.text)
        journal_id = data(journal)["id"]
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
        check("DELETE /journals/{id}", client.delete(f"/api/v1/journals/{journal_id}", headers=auth).status_code == 200)

        print("\n[goals]")
        goal = client.post(
            "/api/v1/goals",
            headers=auth,
            json={"title": "Learn Rust", "description": "Systems programming", "priority": 2},
        )
        check("POST /goals", goal.status_code in (200, 201), goal.text)
        goal_id = data(goal)["id"]
        check("GET /goals", client.get("/api/v1/goals", headers=auth).status_code == 200)
        check("GET /goals/{id}", client.get(f"/api/v1/goals/{goal_id}", headers=auth).status_code == 200)
        updated = client.put(f"/api/v1/goals/{goal_id}", headers=auth, json={"progress": 50})
        check("PUT /goals/{id}", updated.status_code == 200 and data(updated)["progress"] == 50.0, updated.text)
        metric = client.post(
            f"/api/v1/goals/{goal_id}/metrics",
            headers=auth,
            json={"name": "hours", "metric_type": "NUMBER", "target_value": 100},
        )
        check("POST /goals/{id}/metrics", metric.status_code in (200, 201), metric.text)

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
        # Manual entry point is gone: memories are distilled from journals only.
        manual = client.post(
            "/api/v1/memories",
            headers=auth,
            json={"type": "PREFERENCE", "content": "I prefer dark mode"},
        )
        check("POST /memories 405/404 (manual entry removed)", manual.status_code in (404, 405), manual.text)

        print("\n[insights]")
        check("GET /insights", client.get("/api/v1/insights", headers=auth).status_code == 200)
        reports = client.get("/api/v1/reports", headers=auth)
        check("GET /reports 404 (module removed)", reports.status_code == 404, reports.text)
        generate = client.post(
            "/api/v1/reports/generate",
            headers=auth,
            json={"type": "DAILY", "period_start": "2026-09-01", "period_end": "2026-09-30"},
        )
        check("POST /reports/generate 404 (module removed)", generate.status_code == 404, generate.text)

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
