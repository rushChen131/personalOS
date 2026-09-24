from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone

from tests._env import configure

configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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

    def test_promoted_memory_inherits_category_from_source_journals(self) -> None:
        """Memories are never authored, so the domain comes from their evidence."""
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models.memory import Memory

        entries = [
            "我喜欢用 qlib 做因子回测，比我自己写的快很多。",
            "我发现 qlib 的数据接口设计得很省事。",
            "我决定把 qlib 当成回测的主力工具。",
            "我一直用 qlib 验证投资想法，避免拍脑袋。",
        ]
        for content in entries:
            self.client.post(
                "/api/v1/journals",
                headers=self.headers,
                json={"content": content, "category": "INVESTMENT"},
            )

        async def load() -> list[str]:
            async with SessionLocal() as session:
                rows = await session.scalars(
                    select(Memory.category).where(
                        Memory.user_id == self.user_id,
                        Memory.summary == "qlib",
                    )
                )
                return list(rows)

        categories = asyncio.run(load())
        self.assertTrue(categories, "no memory was promoted for the qlib topic")
        self.assertEqual(set(categories), {"INVESTMENT"})

    def test_in_process_job_registry_and_manual_run(self) -> None:
        from app.jobs.in_process import REGISTRY, dispatcher

        for name in ("memory_analysis", "embedding"):
            self.assertIn(name, REGISTRY)
        # Goals became todos and the progress job went with the progress bar.
        self.assertNotIn("goal_progress", REGISTRY)
        # Reports were retired, then rebuilt on the same tables; the registry key
        # is "report_generation" (the legacy "report" key stays gone).
        self.assertIn("report_generation", REGISTRY)
        for name in ("daily_report", "report"):
            self.assertNotIn(name, REGISTRY)

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


class MemoryCandidateRaceTest(unittest.TestCase):
    """The find-or-create on ``memory_candidates`` must survive an interleaving.

    Jobs drain *after* the HTTP response, so two journals written back-to-back
    by one client still ingest concurrently. The bucket ``SELECT`` cannot see a
    row another transaction is committing, so the loser used to hit the UNIQUE
    index and abort the whole ingest — silently discarding that journal's
    evidence.
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

    def test_losing_the_create_race_adopts_the_winners_bucket(self) -> None:
        """A bucket committed by a competing ingest must be adopted, not fatal."""
        from unittest import mock

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.core.database import SessionLocal
        from app.models.journal import Journal
        from app.models.memory import MemoryCandidate
        from app.services.memory_engine import MemoryEngine, _normalize, _topic_key

        statement = "我喜欢用 raceprobe 做数据分析。"
        topic = _topic_key(_normalize(statement))
        self.assertEqual(topic, "raceprobe", "the probe topic must be the Latin entity")
        signature = f"{topic}|PATTERN"

        async def run() -> dict:
            async with SessionLocal() as session:
                # Stand in for the competing request: its bucket is already
                # committed by the time our ingest runs.
                session.add(
                    MemoryCandidate(
                        user_id=self.user_id,
                        signature=signature,
                        type="PATTERN",
                        topic=topic,
                        content="我习惯用 raceprobe 处理报表。",
                        evidence={},
                        evidence_count=0,
                        confidence=0.0,
                        status="PENDING",
                    )
                )
                await session.commit()
                winner = await session.scalar(
                    select(MemoryCandidate).where(MemoryCandidate.signature == signature)
                )
                winner_id = winner.id

                journal = Journal(user_id=self.user_id, content=statement, category="WORK")
                session.add(journal)
                await session.flush()

                # Force the interleaving: our bucket lookup ran *before* the
                # winner committed, so it sees nothing and tries to create.
                real_scalar = AsyncSession.scalar
                calls = {"n": 0}

                async def racy_scalar(inner_self, *args, **kwargs):
                    calls["n"] += 1
                    if calls["n"] == 1:
                        return None
                    return await real_scalar(inner_self, *args, **kwargs)

                with mock.patch.object(AsyncSession, "scalar", racy_scalar):
                    result = await MemoryEngine().ingest_journal(session, self.user_id, journal)
                await session.commit()

                rows = list(
                    (
                        await session.scalars(
                            select(MemoryCandidate).where(
                                MemoryCandidate.user_id == self.user_id,
                                MemoryCandidate.signature == signature,
                            )
                        )
                    ).all()
                )

            return {
                "result": result,
                "winner_id": winner_id,
                "calls": calls["n"],
                "rows": [(row.id, row.evidence_count, row.status) for row in rows],
            }

        outcome = asyncio.run(run())

        # The racing lookup was genuinely simulated.
        self.assertGreaterEqual(outcome["calls"], 2, "the racing lookup was not simulated")
        self.assertEqual(outcome["result"]["statements"], 1, "the statement was not extracted")

        # Exactly one bucket exists — no duplicate slipped past the UNIQUE index.
        self.assertEqual(len(outcome["rows"]), 1, f"duplicate buckets: {outcome['rows']}")

        row_id, evidence_count, _status = outcome["rows"][0]
        self.assertEqual(row_id, outcome["winner_id"], "the loser created its own bucket")
        self.assertEqual(evidence_count, 1, "the journal's evidence was discarded")

    def test_bucket_creation_survives_a_genuine_concurrent_burst(self) -> None:
        """Four simultaneous ingests of one topic must yield one bucket, no error."""
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models.journal import Journal
        from app.models.memory import MemoryCandidate
        from app.services.memory_engine import MemoryEngine, _normalize, _topic_key

        topic = "burstprobe"
        statements = [
            "我喜欢用 burstprobe 做数据分析。",
            "我习惯用 burstprobe 处理报表。",
            "我偏好 burstprobe 的命令行界面。",
            "我一直在用 burstprobe 做自动化。",
        ]
        for text in statements:
            self.assertEqual(_topic_key(_normalize(text)), topic)

        async def run() -> list[tuple[str, int]]:
            async with SessionLocal() as session:
                journals = []
                for text in statements:
                    journal = Journal(user_id=self.user_id, content=text, category="WORK")
                    session.add(journal)
                    journals.append(journal)
                # Commit first: the per-ingest sessions below are separate
                # connections and cannot see uncommitted rows.
                await session.commit()
                journal_ids = [j.id for j in journals]

                # Every ingest runs against its own session, like four jobs
                # draining at once, so the buckets really do race.
                engine = MemoryEngine()

                async def ingest(journal_id: str) -> None:
                    async with SessionLocal() as inner:
                        loaded = await inner.get(Journal, journal_id)
                        await engine.ingest_journal(inner, self.user_id, loaded)
                        await inner.commit()

                # return_exceptions so a failing ingest is reported as such
                # instead of surfacing as an opaque gather error.
                results = await asyncio.gather(
                    *(ingest(journal_id) for journal_id in journal_ids),
                    return_exceptions=True,
                )
                failures = [repr(r) for r in results if isinstance(r, BaseException)]
                self.assertEqual(failures, [], f"concurrent ingests raised: {failures}")

                rows = list(
                    (
                        await session.scalars(
                            select(MemoryCandidate).where(
                                MemoryCandidate.user_id == self.user_id,
                                MemoryCandidate.signature == f"{topic}|PATTERN",
                            )
                        )
                    ).all()
                )
                return [(row.id, row.evidence_count) for row in rows]

        rows = asyncio.run(run())

        self.assertEqual(len(rows), 1, f"the burst produced {len(rows)} buckets: {rows}")
        self.assertEqual(rows[0][1], 4, "evidence from concurrent ingests was lost")


if __name__ == "__main__":
    unittest.main()
