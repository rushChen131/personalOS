"""Live checks that need a real server, a real database and real HTTP.

Run from backend/:  .venv/Scripts/python.exe scripts/live_check.py

Why this exists
---------------
``tests/`` drives everything in-process through ``TestClient``, which runs
FastAPI's dependency teardown *before* the response reaches the caller. Anything
that depends on that ordering -- most importantly "is a delete durable by the
time it reports success?" -- cannot be reproduced there, so a test for it would
pass no matter what. This script starts its own uvicorn on :8002 (never touching
a dev server on :8000), drives it over HTTP, and reads the database directly for
the rows SQLite will not cascade on its own.

Every section cleans up after itself and never modifies a pre-existing row.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PORT = 8002
BASE = f"http://127.0.0.1:{PORT}/api/v1"
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "personalos.db"

# This box has an ambient HTTP_PROXY; 127.0.0.1 must bypass it or we get a 502.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

results: list[tuple[bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append((ok, label))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  <- {detail}" if not ok and detail else ""))


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=payload, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with OPENER.open(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def wait_for_health(deadline: float = 45.0) -> bool:
    end = time.time() + deadline
    while time.time() < end:
        try:
            status, _ = call("GET", "/health")
            if status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass  # not listening yet
        time.sleep(0.5)
    return False


def login() -> str:
    status, body = call(
        "POST", "/auth/login", {"email": "demo@personalos.local", "password": "demo1234"}
    )
    if status != 200:
        raise SystemExit(f"login failed: {status} {body}")
    return body["data"]["access_token"]


def listed_memory_ids(token: str) -> set[str]:
    """Dashed ids normalised to the dashless form the rows actually store.

    ``UUIDType`` writes 32-char hex on SQLite while the API returns a dashed
    UUID, so comparing raw values would always be False -- a check that can
    never fail is worse than no check.
    """
    _, body = call("GET", "/memories", token=token)
    return {row["id"].replace("-", "") for row in body["data"]}


def count(connection: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    return connection.execute(sql, args).fetchone()[0]


# --------------------------------------------------------------------------- #
# 1. The todo contract (goal -> todo rename, 2026-09-24)
# --------------------------------------------------------------------------- #
def check_todos(token: str) -> None:
    print("\n[1/3] todo contract")

    status, _ = call("GET", "/goals", token=token)
    check("GET /goals -> 404", status == 404, str(status))

    status, body = call("POST", "/todos", {"title": "live-check todo", "category": "WORK"}, token)
    check("POST /todos -> 200", status == 200, str(body)[:200])
    todo = body["data"]
    todo_id = todo["id"]
    check("completed_at starts null", todo.get("completed_at") is None, str(todo))
    check("no legacy progress field", "progress" not in todo, str(todo))
    check("no legacy status field", "status" not in todo, str(todo))

    try:
        status, body = call("PUT", f"/todos/{todo_id}", {"completed": True}, token)
        check("checking it stamps completed_at", status == 200 and body["data"]["completed_at"], str(body)[:200])
        status, body = call("PUT", f"/todos/{todo_id}", {"completed": False}, token)
        check("unchecking clears it", status == 200 and body["data"]["completed_at"] is None)

        status, body = call("PUT", f"/todos/{todo_id}", {"completed": True}, token)
        open_only = call("GET", "/todos?completed=false", token=token)[1]["data"]
        check("?completed=false excludes it", all(t["id"] != todo_id for t in open_only))
        done_only = call("GET", "/todos?completed=true", token=token)[1]["data"]
        check("?completed=true includes it", any(t["id"] == todo_id for t in done_only))

        status, _ = call("GET", "/todos?completed=notabool", token=token)
        check("?completed=notabool -> 422", status == 422, str(status))
        status, _ = call("POST", f"/todos/{todo_id}/metrics", {"name": "x", "metric_type": "NUMBER"}, token)
        check("POST /todos/{id}/metrics -> 404", status == 404, str(status))
    finally:
        call("DELETE", f"/todos/{todo_id}", token=token)


# --------------------------------------------------------------------------- #
# 2. A delete must be durable before it reports success
# --------------------------------------------------------------------------- #
def check_journal_delete(token: str, connection: sqlite3.Connection) -> None:
    """Regression for the stale-read window fixed on 2026-09-29.

    ``get_db`` commits after ``yield``, and FastAPI runs that teardown only once
    the response is on the wire. A repository that merely *marks* the row
    (``session.delete`` without a flush) therefore reports success while the row
    is still there, and a client that refreshes immediately sees it come back.

    It also covers the evidence edge. ``MemorySource.source_id`` is a plain
    polymorphic String with no ForeignKey, so nothing cascades and the
    repository has to cut the edge by hand; without that the rows survive
    pointing at a journal that no longer exists.
    """
    print("\n[2/3] journal delete is durable, and cuts its evidence edge")

    status, body = call(
        "POST", "/journals", {"content": "live-check journal", "title": "live-check"}, token
    )
    check("POST /journals -> 200", status == 200, str(body)[:200])
    journal_id = body["data"]["id"]

    # A throwaway memory whose only evidence is this journal, so the edge can be
    # watched disappearing. Rows store ids as 32-char dashless hex.
    memory_id = uuid.uuid4().hex
    user_id = connection.execute(
        "SELECT id FROM users WHERE email = 'demo@personalos.local'"
    ).fetchone()["id"]
    try:
        connection.execute(
            """
            INSERT INTO memories (id, user_id, type, category, content, summary,
                                  confidence, importance, source_count, metadata)
            VALUES (?, ?, 'FACT', 'WORK', 'live-check evidence memory', 'live-check',
                    0.99, 0.99, 1, '{}')
            """,
            (memory_id, user_id),
        )
        # 'JOURNAL' uppercase, and the dashed id: exactly what MemoryEngine
        # writes. Lowercase 'journal' here would make the edge invisible to the
        # very cleanup this section exists to verify.
        connection.execute(
            """
            INSERT INTO memory_sources (id, memory_id, source_type, source_id, relevance)
            VALUES (?, ?, 'JOURNAL', ?, 1.0)
            """,
            (uuid.uuid4().hex, memory_id, journal_id),
        )
        connection.commit()

        def evidence_rows() -> int:
            return count(
                connection,
                "SELECT COUNT(*) FROM memory_sources "
                "WHERE source_type = 'JOURNAL' AND source_id = ?",
                (journal_id,),
            )

        check("the evidence row exists before the delete", evidence_rows() == 1, f"{evidence_rows()} rows")

        status, _ = call("DELETE", f"/journals/{journal_id}", token=token)
        check("DELETE /journals/{id} -> 200", status == 200, str(status))

        status, _ = call("GET", f"/journals/{journal_id}", token=token)
        check("gone on the very next read", status == 404, f"got {status} -- the delete was not flushed")

        _, listing = call("GET", "/journals?limit=100", token=token)
        check("gone from the list too", journal_id not in [row["id"] for row in listing["data"]])

        check(
            "its evidence row is gone, not left dangling",
            evidence_rows() == 0,
            f"{evidence_rows()} dangling -- JournalRepository.delete did not cut the edge",
        )
        survivors = count(connection, "SELECT COUNT(*) FROM memories WHERE id = ?", (memory_id,))
        check("the memory itself survives losing one source", survivors == 1, f"{survivors} rows")
    finally:
        connection.execute("DELETE FROM memory_sources WHERE memory_id = ?", (memory_id,))
        connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        connection.commit()
        call("DELETE", f"/journals/{journal_id}", token=token)


# --------------------------------------------------------------------------- #
# 3. Memory delete, including the edges SQLite will not cascade
# --------------------------------------------------------------------------- #
def check_memory_delete(token: str, connection: sqlite3.Connection) -> None:
    print("\n[3/3] memory delete cuts both edges by hand")

    # A throwaway memory rather than an existing one: this must never destroy
    # real data. Stored ids are 32-char dashless hex.
    memory_id = uuid.uuid4().hex
    candidate_id = uuid.uuid4().hex
    user_id = connection.execute(
        "SELECT id FROM users WHERE email = 'demo@personalos.local'"
    ).fetchone()["id"]
    try:
        # High importance on purpose: GET /memories is capped at 50 rows ordered
        # by importance DESC, so a mid-range value would fall off the first page
        # and make both list assertions pass vacuously.
        connection.execute(
            """
            INSERT INTO memories (id, user_id, type, category, content, summary,
                                  confidence, importance, source_count, metadata)
            VALUES (?, ?, 'FACT', 'WORK', 'live-check memory', 'live-check', 0.99, 0.99, 2, '{}')
            """,
            (memory_id, user_id),
        )
        for index in range(2):
            connection.execute(
                """
                INSERT INTO memory_sources (id, memory_id, source_type, source_id, relevance)
                VALUES (?, ?, 'JOURNAL', ?, 1.0)
                """,
                (uuid.uuid4().hex, memory_id, f"live-check-source-{index}"),
            )
        connection.execute(
            """
            INSERT INTO memory_candidates (id, user_id, signature, type, content, topic,
                                           evidence_count, confidence, status, evidence,
                                           promoted_memory_id)
            VALUES (?, ?, ?, 'FACT', 'live-check candidate', 'live-check', 1, 0.9, 'PROMOTED',
                    '{}', ?)
            """,
            (candidate_id, user_id, f"LIVE-CHECK|{candidate_id[:8]}", memory_id),
        )
        connection.commit()

        check("it is visible before the delete", memory_id in listed_memory_ids(token))

        status, body = call("DELETE", f"/memories/{memory_id}", token=token)
        check("DELETE /memories/{id} -> 200", status == 200, str(body)[:200])
        status, _ = call("GET", f"/memories/{memory_id}", token=token)
        check("gone on the very next read", status == 404, f"got {status}")
        check("gone from the list too", memory_id not in listed_memory_ids(token))
        status, _ = call("DELETE", f"/memories/{memory_id}", token=token)
        check("a second DELETE -> 404", status == 404, str(status))

        left = count(connection, "SELECT COUNT(*) FROM memories WHERE id = ?", (memory_id,))
        check("the memories row is gone", left == 0, f"{left} left")
        orphans = count(
            connection, "SELECT COUNT(*) FROM memory_sources WHERE memory_id = ?", (memory_id,)
        )
        check("memory_sources removed, no orphans", orphans == 0, f"{orphans} orphans")
        dangling = count(
            connection,
            "SELECT COUNT(*) FROM memory_candidates WHERE promoted_memory_id = ?",
            (memory_id,),
        )
        check("promoted_memory_id NULLed, not left dangling", dangling == 0, f"{dangling} dangling")
        detached = connection.execute(
            "SELECT promoted_memory_id FROM memory_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        check(
            "the candidate row itself survives, detached",
            detached is not None and detached["promoted_memory_id"] is None,
            str(detached),
        )

        status, _ = call("DELETE", "/memories/00000000-0000-0000-0000-000000000000", token=token)
        check("unknown id -> 404", status == 404, str(status))
        status, _ = call("DELETE", "/memories/not-a-uuid", token=token)
        check("malformed id -> 404, not 500", status == 404, str(status))
    finally:
        connection.execute("DELETE FROM memory_candidates WHERE id = ?", (candidate_id,))
        connection.execute("DELETE FROM memory_sources WHERE memory_id = ?", (memory_id,))
        connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        connection.commit()


def main() -> int:
    print(f"starting uvicorn on :{PORT}")
    server = subprocess.Popen(
        [
            str(ROOT / ".venv" / "Scripts" / "python.exe"),
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(ROOT),
        # The child reads ``.env`` unconditionally, so without this it would
        # append probe traffic to the *real* dev log -- and two processes
        # rotating the same file can interleave or corrupt it. An empty
        # LOG_FILE turns file logging off (env vars outrank ``.env``).
        env={**os.environ, "LOG_FILE": ""},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    connection: sqlite3.Connection | None = None
    try:
        if not wait_for_health():
            print("server never became healthy", file=sys.stderr)
            return 1
        print("server healthy\n")

        connection = sqlite3.connect(str(DB))
        connection.row_factory = sqlite3.Row
        token = login()

        check_todos(token)
        check_journal_delete(token, connection)
        check_memory_delete(token, connection)
    finally:
        if connection is not None:
            connection.close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    failed = [label for ok, label in results if not ok]
    print("\n" + "=" * 60)
    print(f"PASSED: {len(results) - len(failed)}   FAILED: {len(failed)}")
    for label in failed:
        print(f"  FAILED  {label}")
    if failed:
        return 1
    print("All live checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
