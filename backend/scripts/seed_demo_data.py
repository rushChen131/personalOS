"""Populate a running PersonalOS instance with a realistic demo dataset.

Everything is written through the HTTP API, so the real Journal -> Candidate ->
Memory pipeline runs exactly as it would for a live user. Nothing is inserted
directly into the database.

Journals are the single authored input, so this script only writes journals
(plus a small checklist of todos). Memories are derived by the jobs that fire on
journal creation.

Every seeded journal and todo carries a life-domain category (投资、工作、学习…);
memories inherit the dominant category of the journals they were distilled from.

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

    Only ``/journals`` and ``/todos`` expose a DELETE endpoint today, so other
    collections cannot be cleared over HTTP. Rather than silently leaving stale
    rows behind, this reports what it can remove and tells the caller to rebuild
    the database when a fully clean slate is required.
    """
    removable = ("/journals", "/todos")
    skipped: list[str] = []
    removed = 0
    for path in ("/journals", "/todos", "/memories"):
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

    # ------------------------------------------------------------------- todos
    # A checklist item is title + category + completion. Nothing here carries a
    # percentage: `completed_at` is the single source of truth for done/not-done.
    print("\n[todos]")
    todos = {}
    for title, category, target in (
        (
            "Ship AgentScope v1.0 release notes",
            "WORK",
            (today + timedelta(days=7)).isoformat(),
        ),
        (
            "Finish 'Thinking in Systems'",
            "LEARNING",
            (today + timedelta(days=14)).isoformat(),
        ),
        (
            "Book the 10K race entry",
            "HEALTH",
            (today + timedelta(days=30)).isoformat(),
        ),
        (
            "Rebalance the index-fund position",
            "INVESTMENT",
            (today + timedelta(days=45)).isoformat(),
        ),
        (
            "Write the weekly retrospective",
            "LIFE",
            None,
        ),
    ):
        todo = client.data(
            client.post(
                "/todos",
                {"title": title, "category": category, "target_date": target},
            )
        )
        todos[title] = todo["id"]
        print(f"  + todo     [{category:<10}] {title}")

    # Check one item off, so the demo checklist shows both states and the report
    # narrative has a completed todo to mention.
    client.put(f"/todos/{todos['Write the weekly retrospective']}", {"completed": True})
    print("  ~ done     Write the weekly retrospective")

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
    # Each entry carries a life-domain category (投资/工作/学习…). Memories are
    # not authored, so the MemoryEngine inherits the dominant category of the
    # journals behind each promoted memory — the AgentScope bucket below is all
    # WORK, so its memory should come out as WORK rather than the OTHER default.
    journal_specs = [
        # (days_ago, title, content, mood, category)
        (
            1,
            "AgentScope architecture research",
            "Spent two hours reading up on AgentScope architecture today. "
            "I am using AgentScope for a multi-agent orchestration prototype and the "
            "message bus design is the part I keep coming back to.",
            "focused",
            "WORK",
        ),
        (
            1,
            "AgentScope tool-loop refactor",
            "The AgentScope tool-loop refactor is finally clicking. I bounded the tool "
            "loop to three rounds and the behaviour is much easier to reason about. "
            "I think AgentScope is the right foundation for this.",
            "satisfied",
            "WORK",
        ),
        (
            2,
            "AgentScope architecture deep dive",
            "Went deeper into the AgentScope architecture again. I prefer AgentScope's "
            "explicit tool registry over the more magical frameworks I have tried.",
            "curious",
            "WORK",
        ),
        (
            3,
            "AgentScope deployment pipeline",
            "Wired up the AgentScope deployment pipeline. I am deploying AgentScope "
            "behind a small FastAPI service and the packaging story is still rough.",
            "tired",
            "WORK",
        ),
        (
            4,
            "AgentScope tooling review",
            "Reviewed the AgentScope tooling with the team. I think AgentScope needs a "
            "clearer permission model before other teams adopt it.",
            "thoughtful",
            "WORK",
        ),
        (
            5,
            "AgentScope architecture notes",
            "Wrote up my AgentScope architecture notes. I keep AgentScope notes in a "
            "flat markdown file because a wiki slows me down.",
            "focused",
            "WORK",
        ),
        (
            2,
            "PersonalOS memory pipeline work",
            "Worked on the PersonalOS memory pipeline. I am extracting memories straight "
            "from the journals I write rather than entering them by hand.",
            "satisfied",
            "WORK",
        ),
        (
            2,
            "Strength training",
            "Strength session today. I train three times a week and I run on the "
            "off days, which keeps my energy steady.",
            "energised",
            "HEALTH",
        ),
        (
            1,
            "Morning run",
            "Easy morning run before work. I prefer running early because the city is "
            "quiet and I think more clearly afterwards.",
            "good",
            "HEALTH",
        ),
        (
            4,
            "Long run",
            "Long run on the weekend. I usually keep these slow and conversational to "
            "protect my knees.",
            "good",
            "HEALTH",
        ),
        (
            2,
            "Read 'Thinking in Systems'",
            "Read another chapter of Thinking in Systems. I read before bed most nights "
            "and it has replaced scrolling almost entirely.",
            "calm",
            "LEARNING",
        ),
        (
            5,
            "Read 'The Design of Everyday Things'",
            "Finished The Design of Everyday Things. I like books that give me a lens I "
            "can apply the next morning at work.",
            "curious",
            "LEARNING",
        ),
        (
            1,
            "Sprint planning",
            "Sprint planning for the AgentScope release. I planned aggressively and I "
            "need to be honest that the scope is probably too big.",
            "focused",
            "WORK",
        ),
        (
            3,
            "Code review session",
            "Long code review session. I am reviewing more than I am writing right now "
            "and I do not enjoy that ratio.",
            "tired",
            "WORK",
        ),
        (
            4,
            "Weekly retrospective",
            "Weekly retrospective. I realised I have been skipping my evening walks and "
            "that my sleep got worse because of it.",
            "thoughtful",
            "LIFE",
        ),
        (
            5,
            "Decided to drop the graph DB spike",
            "I decided to drop the graph database spike. I was spending more time "
            "learning the tool than solving the problem.",
            "relieved",
            "WORK",
        ),
        (
            2,
            "Shipped vector retrieval",
            "Shipped the vector retrieval path. I always feel better after shipping "
            "something tangible rather than reading about it.",
            "proud",
            "WORK",
        ),
        (
            4,
            "Dinner with friends",
            "Dinner with friends. I need these evenings more than I admit and I should "
            "protect them when my calendar gets busy.",
            "happy",
            "SOCIAL",
        ),
        (
            5,
            "Budget review",
            "Monthly budget review. I track spending on the first weekend of the month "
            "because otherwise I avoid looking at it entirely.",
            "neutral",
            "FINANCE",
        ),
        (
            3,
            "Portfolio rebalance",
            "Rebalanced the portfolio this evening. I invest on a fixed schedule rather "
            "than reacting to the news, because I know my own timing is not good.",
            "calm",
            "INVESTMENT",
        ),
        (
            6,
            "Index fund fee research",
            "Compared index fund fee structures. I prefer broad index funds over picking "
            "individual stocks because I do not want to watch them every day.",
            "curious",
            "INVESTMENT",
        ),
        (
            3,
            "Weekend reflection",
            "Good week overall. I wrote every day, which is the habit I am most proud of "
            "sustaining this quarter.",
            "good",
            "LIFE",
        ),
    ]
    created = 0
    for days_ago, title, content, mood, category in journal_specs:
        occurred = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=4)
        client.post(
            "/journals",
            {
                "title": title,
                "content": content,
                "mood": mood,
                "category": category,
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
        ("/todos", "todos"),
        ("/journals", "journals"),
        ("/memories", "memories"),
    ):
        items = client.data(client.get(path))
        print(f"  {label:<10} {len(items)}")

    # Confirms the category field round-trips through the API, and that promoted
    # memories inherited a real domain rather than the OTHER default.
    print("\n[by category]")
    for path, label in (("/journals", "journals"), ("/todos", "todos"), ("/memories", "memories")):
        counts: dict[str, int] = {}
        for item in client.data(client.get(path)):
            key = item.get("category") or "MISSING"
            counts[key] = counts.get(key, 0) + 1
        breakdown = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        print(f"  {label:<10} {breakdown or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
