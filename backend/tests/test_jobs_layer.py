from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from tests._env import configure

configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _Journal(jid: str, title: str, content: str, when: datetime, mood: str | None = None):
    """An in-memory Journal stand-in.

    The insight rules are pure functions over journal *attributes*, so they can
    be exercised without a session — the rules themselves never touch the DB.
    """
    from app.models.journal import Journal

    return Journal(
        id=jid,
        user_id="test-user",
        title=title,
        content=content,
        mood=mood,
        occurred_at=when,
        created_at=when,
    )


class JobsLayerTest(unittest.TestCase):
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

    def test_journal_creation_does_not_promote_single_entry_to_memory(self) -> None:
        """§83: a single Journal must never become a Memory (candidate staging)."""
        before = len(self.client.get("/api/v1/memories", headers=self.headers).json()["data"])
        self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": "今天做了点零散的事，没什么特别的；只有一句话值得记住：我喜欢用 zeta 做实验。"},
        )
        after = self.client.get("/api/v1/memories", headers=self.headers).json()["data"]
        self.assertEqual(len(after), before, "a lone journal entry must not create a memory")

    def test_repeated_events_promote_memory_candidate(self) -> None:
        """§83: repeated, varied journal evidence promotes a candidate into a Memory."""
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models.memory import MemoryCandidate

        entries = [
            "我喜欢用 AgentScope 搭多智能体系统，分工很清楚。",
            "我发现 AgentScope 的架构很适合做工具编排。",
            "我决定深入学习 AgentScope 的 tooling 设计。",
            "我一直用 AgentScope 做部署验证，很稳。",
        ]
        before = len(self.client.get("/api/v1/memories", headers=self.headers).json()["data"])
        for content in entries:
            self.client.post(
                "/api/v1/journals",
                headers=self.headers,
                json={"content": content},
            )
        after = self.client.get("/api/v1/memories", headers=self.headers).json()["data"]
        self.assertGreater(len(after), before, "repeated evidence did not promote a memory")

        async def load() -> list[MemoryCandidate]:
            async with SessionLocal() as session:
                rows = await session.scalars(
                    select(MemoryCandidate).where(
                        MemoryCandidate.user_id == self.user_id,
                        MemoryCandidate.topic == "agentscope",
                    )
                )
                return list(rows)

        candidates = asyncio.run(load())
        self.assertTrue(candidates, "no candidate bucket was created for the topic")
        promoted = [c for c in candidates if c.status == "PROMOTED"]
        self.assertTrue(promoted, "candidate was not marked PROMOTED")
        # Assert on the bucket that accumulated the evidence, not an arbitrary one.
        self.assertGreaterEqual(max(c.evidence_count for c in promoted), 4)
        self.assertIsNotNone(promoted[0].promoted_memory_id)

    def test_insight_engine_flags_stagnant_goal(self) -> None:
        from app.core.database import SessionLocal
        from app.repositories.insight_report_repository import InsightRepository
        from app.services.insight_engine import InsightEngine

        overdue = datetime.now(timezone.utc).date() - timedelta(days=3)
        goal = self.client.post(
            "/api/v1/goals",
            headers=self.headers,
            json={"title": "Stalled certification", "target_date": overdue.isoformat()},
        )
        self.assertEqual(goal.status_code, 200)

        # The stalled-goal rule reports goals that are ACTIVE but unmentioned, so
        # give the window some journals the goal does not appear in. Journal
        # entries are the only input the engine reads now — events are gone.
        for i in range(3):
            self.client.post(
                "/api/v1/journals",
                headers=self.headers,
                json={"title": f"Routine day {i}", "content": f"I spent the afternoon tidying notes {i}."},
            )

        async def run() -> None:
            async with SessionLocal() as session:
                engine = InsightEngine(InsightRepository())
                await engine.generate(session, self.user_id, period_days=14)
                await session.commit()

        asyncio.run(run())
        # Assert against the persisted feed, not generate()'s return value: an
        # insight whose title already exists is refreshed rather than returned,
        # and earlier tests in this class share the same demo user.
        insights = self.client.get("/api/v1/insights", headers=self.headers).json()["data"]
        self.assertIn("RISK", [i["insight_type"] for i in insights])
        self.assertIn(
            "Goal stalled: Stalled certification",
            [i["title"] for i in insights],
        )

    def test_insight_engine_reads_journals_not_events(self) -> None:
        """The engine must have no Event dependency at all."""
        import app.services.insight_engine as ie

        self.assertFalse(hasattr(ie, "Event"), "insight engine still imports the Event model")

        from app.models.journal import Journal
        from app.services.insight_engine import InsightEngine

        entry = Journal(
            id="j1",
            user_id="u1",
            title="Rust ownership",
            content="I am learning Rust ownership. The borrow checker finally makes sense.",
        )
        self.assertIn("rust", InsightEngine._topics(entry))

    def test_insight_engine_detects_recurring_topic(self) -> None:
        """Three entries on one subject must surface as a TREND.

        Regression guard: the day-spread requirement used to reject entries
        written in a single sitting, which is how journals are actually written.
        """
        from app.services.insight_engine import InsightEngine

        now = datetime.now(timezone.utc)
        entries = [
            _Journal("j1", "Rust ownership", "I am learning Rust ownership.", now),
            _Journal("j2", "Rust traits", "I spent the evening on Rust traits.", now),
            _Journal("j3", "Rust borrow checker", "Rust ownership clicked today.", now),
            _Journal("j4", "Morning run", "I went for a long run this morning.", now),
            _Journal("j5", "Design reading", "I read a chapter of the design book.", now),
        ]
        candidates = InsightEngine._detect_recurring_topics(entries, now)
        titles = [c["title"] for c in candidates]
        self.assertIn("Recurring focus: rust", titles)

        trend = next(c for c in candidates if c["title"] == "Recurring focus: rust")
        self.assertEqual(trend["insight_type"], "TREND")
        self.assertGreaterEqual(trend["confidence"], 0.5)

    def test_insight_engine_detects_mood_trend_both_directions(self) -> None:
        from app.services.insight_engine import InsightEngine

        now = datetime.now(timezone.utc)

        def entry(i: int, mood: str):
            return _Journal(f"m{i}", f"day {i}", "A quiet day.", now, mood=mood)

        low = InsightEngine._detect_mood_trend(
            [entry(1, "tired"), entry(2, "drained"), entry(3, "anxious"), entry(4, "low"), entry(5, "good")],
            now,
        )
        self.assertIn("RISK", [c["insight_type"] for c in low])
        self.assertIn("Mood trending low", [c["title"] for c in low])

        high = InsightEngine._detect_mood_trend(
            [entry(1, "good"), entry(2, "good"), entry(3, "good"), entry(4, "happy"), entry(5, "calm")],
            now,
        )
        self.assertIn("Consistently 'good'", [c["title"] for c in high])

    def test_insight_engine_does_not_stack_duplicate_titles(self) -> None:
        """The engine fires on every journal write; repeated runs must converge."""
        from app.core.database import SessionLocal
        from app.repositories.insight_report_repository import InsightRepository
        from app.services.insight_engine import InsightEngine

        for i in range(3):
            self.client.post(
                "/api/v1/journals",
                headers=self.headers,
                json={"title": f"Rust session {i}", "content": f"I am learning Rust ownership, round {i}."},
            )

        async def run_thrice() -> int:
            async with SessionLocal() as session:
                for _ in range(3):
                    engine = InsightEngine(InsightRepository())
                    await engine.generate(session, self.user_id, period_days=14)
                    await session.commit()
            return 0

        asyncio.run(run_thrice())
        insights = self.client.get("/api/v1/insights", headers=self.headers).json()["data"]
        titles = [i["title"] for i in insights]
        for title in set(titles):
            self.assertEqual(
                titles.count(title),
                1,
                f"insight title {title!r} was duplicated across engine runs",
            )

    def test_in_process_job_registry_and_manual_run(self) -> None:
        from app.jobs.in_process import REGISTRY, dispatcher

        for name in ("goal_progress", "memory_analysis", "insight_analysis", "embedding"):
            self.assertIn(name, REGISTRY)
        for name in ("daily_report", "report"):
            self.assertNotIn(name, REGISTRY, "report jobs were removed with the module")

        result = asyncio.run(dispatcher.run_job("memory_analysis", self.user_id, {}))
        self.assertIn("skipped", result, "memory_analysis without a journal_id must skip cleanly")
        unknown = asyncio.run(dispatcher.run_job("does_not_exist", self.user_id, {}))
        self.assertIn("error", unknown)

    def test_worker_settings_defined(self) -> None:
        from app.jobs.worker import WorkerSettings

        self.assertTrue(hasattr(WorkerSettings, "functions"))
        names = {getattr(fn, "__name__", "") for fn in WorkerSettings.functions}
        self.assertIn("run_job", names)

    def test_memory_compaction_prunes_dead_candidates(self) -> None:
        """Dead candidates are pruned; fresh and promoted ones are retained."""
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.jobs.handlers import MemoryCompactionJob
        from app.models.memory import MemoryCandidate

        now = datetime.now(timezone.utc)
        cases = [
            ("job_layer_dead_pending", "PENDING", now - timedelta(days=200)),
            ("job_layer_fresh_pending", "PENDING", now - timedelta(days=5)),
            ("job_layer_old_promoted", "PROMOTED", now - timedelta(days=400)),
        ]

        async def run() -> dict:
            async with SessionLocal() as session:
                for signature, status, seen in cases:
                    session.add(
                        MemoryCandidate(
                            user_id=self.user_id,
                            signature=signature,
                            type="PATTERN",
                            content="c",
                            topic=signature,
                            status=status,
                            last_seen_at=seen,
                        )
                    )
                await session.commit()
                result = await MemoryCompactionJob().run(session, self.user_id, {})
                await session.commit()
                remaining = list(
                    (
                        await session.scalars(
                            select(MemoryCandidate.signature).where(
                                MemoryCandidate.signature.like("job_layer_%")
                            )
                        )
                    ).all()
                )
                return {"result": result, "remaining": sorted(remaining)}

        outcome = asyncio.run(run())
        self.assertEqual(outcome["result"]["pruned_candidates"], 1)
        self.assertEqual(outcome["remaining"], ["job_layer_fresh_pending", "job_layer_old_promoted"])


if __name__ == "__main__":
    unittest.main()
