"""Populate a running PersonalOS instance with a realistic demo dataset.

Everything is written through the HTTP API, so the real Journal -> Candidate ->
Memory pipeline and the goal-progress job run exactly as
they would for a live user. Nothing is inserted directly into the database.

Journals are the single authored input, so this script only writes journals (and
goals/metrics). Memories and goal progress are derived by the jobs
that fire on journal creation.

    cd backend && .venv/Scripts/python.exe scripts/seed_demo_data.py

Options:
    --base-url http://127.0.0.1:8000   API origin
    --email    demo@personalos.local   demo account
    --password demo1234
    --reset                            delete the demo user's existing data first
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        # Bypass any ambient HTTP proxy: this script only ever talks to the local
        # dev server, and a corporate/system proxy turns 127.0.0.1 into a 502.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}/api/v1{path}"
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=payload, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self._opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()
            raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc

    def get(self, path: str) -> dict:
        return self._call("GET", path)

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._call("POST", path, body or {})

    def put(self, path: str, body: dict) -> dict:
        return self._call("PUT", path, body)

    def delete(self, path: str) -> dict:
        return self._call("DELETE", path)

    def data(self, response: dict):
        if not response.get("success"):
            raise RuntimeError(f"API error: {response}")
        return response["data"]

    def login(self, email: str, password: str) -> None:
        self.token = self.data(self.post("/auth/login", {"email": email, "password": password}))["access_token"]


def reset_demo_data(client: ApiClient) -> None:
    """Remove the demo user's existing records so re-seeding is idempotent.

    Only ``/journals`` and ``/goals`` expose a DELETE endpoint today, so other
    collections cannot be cleared over HTTP. Rather than silently leaving stale
    rows behind, this reports what it can remove and tells the caller to rebuild
    the database when a fully clean slate is required.
    """
    removable = ("/journals", "/goals")
    skipped: list[str] = []
    removed = 0
    for path in ("/journals", "/goals", "/memories"):
        items = client.data(client.get(path))
        if path not in removable:
            if items:
                skipped.append(f"{path} ({len(items)})")
            continue
        for item in items:
            client.delete(f"{path}/{item['id']}")
            removed += 1
    print(f"  reset: removed {removed} records")
    if skipped:
        print(f"  reset: NO delete endpoint for {', '.join(skipped)} — recreate the DB for a clean slate")


def seed(client: ApiClient) -> None:
    today = datetime.now(timezone.utc).date()
    weekday = today.weekday()

    # ------------------------------------------------------------------- goals
    print("\n[goals]")
    goals = {}
    for title, why, target in (
        (
            "Ship AgentScope v1.0",
            "Get the framework stable enough for other teams to adopt",
            (today + timedelta(days=45)).isoformat(),
        ),
        (
            "Read 12 books this year",
            "Sustained input keeps my thinking sharp",
            (today + timedelta(days=100)).isoformat(),
        ),
        (
            "Run a sub-50 minute 10K",
            "Baseline fitness and a concrete measurable target",
            (today + timedelta(days=75)).isoformat(),
        ),
    ):
        goal = client.data(client.post("/goals", {"title": title, "why": why, "target_date": target}))
        goals[title] = goal["id"]
        print(f"  + goal     {title}")

    # Attach a measurable metric to one goal (exercises the goal page context).
    client.post(
        f"/goals/{goals['Run a sub-50 minute 10K']}/metrics",
        {
            "name": "Weekly distance",
            "metric_type": "NUMBER",
            "current_value": 24,
            "target_value": 35,
            "unit": "km",
        },
    )
    print("  + metric   Weekly distance (24/35 km)")

    # ---------------------------------------------------------------- journals
    # Journals are the only authored input. Each entry is written as a short
    # first-person paragraph, because the extractor pulls individually-stated
    # facts out of the body text.
    #
    # The AgentScope topic is deliberately repeated across many distinct entries
    # so the §83 candidate pipeline accumulates real evidence and promotes a
    # long-term Memory. Promotion needs all three of:
    #   * >= MIN_EVIDENCE_COUNT(3) matching statements,
    #   * >= MIN_DISTINCT_TITLES(3) *distinct* statement texts,
    #   * confidence >= PROMOTION_THRESHOLD(0.75).
    # Confidence rises with volume, so a bucket that only just clears the bar
    # (3 statements -> 0.69) does NOT promote. Each AgentScope entry therefore
    # carries at least one first-person statement mentioning AgentScope, which
    # also keeps the bucket comfortably above the threshold.
    print("\n[journals]")
    journal_specs = [
        # (days_ago, title, content, mood)
        (
            1,
            "AgentScope architecture research",
            "Spent two hours reading up on AgentScope architecture today. "
            "I am using AgentScope for a multi-agent orchestration prototype and the "
            "message bus design is the part I keep coming back to.",
            "focused",
        ),
        (
            1,
            "AgentScope tool-loop refactor",
            "The AgentScope tool-loop refactor is finally clicking. I bounded the tool "
            "loop to three rounds and the behaviour is much easier to reason about. "
            "I think AgentScope is the right foundation for this.",
            "satisfied",
        ),
        (
            2,
            "AgentScope architecture deep dive",
            "Went deeper into the AgentScope architecture again. I prefer AgentScope's "
            "explicit tool registry over the more magical frameworks I have tried.",
            "curious",
        ),
        (
            3,
            "AgentScope deployment pipeline",
            "Wired up the AgentScope deployment pipeline. I am deploying AgentScope "
            "behind a small FastAPI service and the packaging story is still rough.",
            "tired",
        ),
        (
            4,
            "AgentScope tooling review",
            "Reviewed the AgentScope tooling with the team. I think AgentScope needs a "
            "clearer permission model before other teams adopt it.",
            "thoughtful",
        ),
        (
            5,
            "AgentScope architecture notes",
            "Wrote up my AgentScope architecture notes. I keep AgentScope notes in a "
            "flat markdown file because a wiki slows me down.",
            "focused",
        ),
        (
            2,
            "PersonalOS memory pipeline work",
            "Worked on the PersonalOS memory pipeline. I am extracting memories straight "
            "from the journals I write rather than entering them by hand.",
            "satisfied",
        ),
        (
            2,
            "Strength training",
            "Strength session today. I train three times a week and I run on the "
            "off days, which keeps my energy steady.",
            "energised",
        ),
        (
            1,
            "Morning run",
            "Easy morning run before work. I prefer running early because the city is "
            "quiet and I think more clearly afterwards.",
            "good",
        ),
        (
            4,
            "Long run",
            "Long run on the weekend. I usually keep these slow and conversational to "
            "protect my knees.",
            "good",
        ),
        (
            2,
            "Read 'Thinking in Systems'",
            "Read another chapter of Thinking in Systems. I read before bed most nights "
            "and it has replaced scrolling almost entirely.",
            "calm",
        ),
        (
            5,
            "Read 'The Design of Everyday Things'",
            "Finished The Design of Everyday Things. I like books that give me a lens I "
            "can apply the next morning at work.",
            "curious",
        ),
        (
            1,
            "Sprint planning",
            "Sprint planning for the AgentScope release. I planned aggressively and I "
            "need to be honest that the scope is probably too big.",
            "focused",
        ),
        (
            3,
            "Code review session",
            "Long code review session. I am reviewing more than I am writing right now "
            "and I do not enjoy that ratio.",
            "tired",
        ),
        (
            4,
            "Weekly retrospective",
            "Weekly retrospective. I realised I have been skipping my evening walks and "
            "that my sleep got worse because of it.",
            "thoughtful",
        ),
        (
            5,
            "Decided to drop the graph DB spike",
            "I decided to drop the graph database spike. I was spending more time "
            "learning the tool than solving the problem.",
            "relieved",
        ),
        (
            2,
            "Shipped vector retrieval",
            "Shipped the vector retrieval path. I always feel better after shipping "
            "something tangible rather than reading about it.",
            "proud",
        ),
        (
            4,
            "Dinner with friends",
            "Dinner with friends. I need these evenings more than I admit and I should "
            "protect them when my calendar gets busy.",
            "happy",
        ),
        (
            5,
            "Budget review",
            "Monthly budget review. I track spending on the first weekend of the month "
            "because otherwise I avoid looking at it entirely.",
            "neutral",
        ),
        (
            3,
            "Weekend reflection",
            "Good week overall. I wrote every day, which is the habit I am most proud of "
            "sustaining this quarter.",
            "good",
        ),
    ]
    created = 0
    for days_ago, title, content, mood in journal_specs:
        occurred = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=4)
        client.post(
            "/journals",
            {
                "title": title,
                "content": content,
                "mood": mood,
                "occurred_at": occurred.isoformat(),
            },
        )
        created += 1
    print(f"  + {created} journals")

    print(f"\n  (weekday={weekday}, seeding complete)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PersonalOS demo data")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--email", default="demo@personalos.local")
    parser.add_argument("--password", default="demo1234")
    parser.add_argument("--reset", action="store_true", help="delete existing demo data first")
    args = parser.parse_args()

    client = ApiClient(args.base_url)
    try:
        client.login(args.email, args.password)
    except RuntimeError as exc:
        print(f"login failed: {exc}", file=sys.stderr)
        return 1
    print(f"authenticated as {args.email} @ {args.base_url}")

    if args.reset:
        reset_demo_data(client)

    seed(client)

    print("\n[verify]")
    for path, label in (
        ("/goals", "goals"),
        ("/journals", "journals"),
        ("/memories", "memories"),
    ):
        items = client.data(client.get(path))
        print(f"  {label:<10} {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
