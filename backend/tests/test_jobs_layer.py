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

    def test_in_process_job_registry_and_manual_run(self) -> None:
        from app.jobs.in_process import REGISTRY, dispatcher

        for name in ("goal_progress", "memory_analysis", "embedding"):
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
