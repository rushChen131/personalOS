from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, timedelta, timezone

from tests._env import configure

configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.report_engine import (  # noqa: E402
    DIMENSION_ALL,
    ReportEngine,
    normalise_dimension,
    period_bounds,
    previous_period_bounds,
)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class PeriodBoundsTest(unittest.TestCase):
    """Pure calendar math — deliberately database-free."""

    def test_daily_bounds_collapse_to_one_day(self) -> None:
        self.assertEqual(period_bounds("DAILY", date(2026, 9, 23)), (date(2026, 9, 23), date(2026, 9, 23)))

    def test_weekly_bounds_start_on_monday(self) -> None:
        # 2026-09-23 is a Wednesday, so the ISO week is Mon 21st .. Sun 27th.
        self.assertEqual(date(2026, 9, 23).weekday(), 2)
        self.assertEqual(period_bounds("WEEKLY", date(2026, 9, 23)), (date(2026, 9, 21), date(2026, 9, 27)))

    def test_weekly_bounds_on_a_sunday_close_that_same_week(self) -> None:
        # Sunday must belong to the week that started six days earlier, not the
        # next one — the classic off-by-one when week starts are mishandled.
        self.assertEqual(period_bounds("WEEKLY", date(2026, 9, 27)), (date(2026, 9, 21), date(2026, 9, 27)))

    def test_monthly_bounds_handle_a_31_day_month(self) -> None:
        self.assertEqual(period_bounds("MONTHLY", date(2026, 9, 23)), (date(2026, 9, 1), date(2026, 9, 30)))

    def test_monthly_bounds_handle_leap_february(self) -> None:
        self.assertEqual(period_bounds("MONTHLY", date(2024, 2, 10)), (date(2024, 2, 1), date(2024, 2, 29)))

    def test_monthly_bounds_handle_a_non_leap_february(self) -> None:
        self.assertEqual(period_bounds("MONTHLY", date(2026, 2, 10)), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_previous_daily_is_yesterday(self) -> None:
        self.assertEqual(previous_period_bounds("DAILY", date(2026, 9, 23)), (date(2026, 9, 22), date(2026, 9, 22)))

    def test_previous_weekly_is_the_prior_iso_week(self) -> None:
        self.assertEqual(previous_period_bounds("WEEKLY", date(2026, 9, 23)), (date(2026, 9, 14), date(2026, 9, 20)))

    def test_previous_monthly_rolls_back_across_the_year_boundary(self) -> None:
        self.assertEqual(previous_period_bounds("MONTHLY", date(2026, 1, 15)), (date(2025, 12, 1), date(2025, 12, 31)))

    def test_unsupported_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            period_bounds("QUARTERLY", date(2026, 9, 23))

    def test_dimension_normalisation_falls_back_to_all(self) -> None:
        self.assertEqual(normalise_dimension(None), DIMENSION_ALL)
        self.assertEqual(normalise_dimension("all"), DIMENSION_ALL)
        self.assertEqual(normalise_dimension("WORK"), "WORK")
        self.assertEqual(normalise_dimension("work"), "WORK")
        # An unknown domain must not silently produce an empty report.
        self.assertEqual(normalise_dimension("NOT_A_CATEGORY"), DIMENSION_ALL)


class ReportSummaryTest(unittest.TestCase):
    """Goals became todos, so the template must say "待办 / todos" (§D8).

    The template is a static method over the fixed ``content`` contract, so it
    is exercised without a database and without depending on the user's locale.
    """

    CONTENT = {
        "journal_count": 2,
        "active_days": 1,
        "category_breakdown": {"WORK": 2},
        "mood_breakdown": {},
        "todos": [
            {
                "id": "t1",
                "title": "写周报",
                "category": "WORK",
                "completed": False,
                "completed_at": None,
            }
        ],
        "memories": [],
    }

    def test_chinese_summary_mentions_todos(self) -> None:
        summary = ReportEngine._render_summary(
            "DAILY", date(2026, 9, 23), date(2026, 9, 23), self.CONTENT, "zh"
        )
        self.assertIn("涉及待办", summary)
        self.assertNotIn("目标", summary)

    def test_english_summary_mentions_todos(self) -> None:
        summary = ReportEngine._render_summary(
            "DAILY", date(2026, 9, 23), date(2026, 9, 23), self.CONTENT, "en"
        )
        self.assertIn("Todos touched", summary)
        self.assertNotIn("Goals", summary)


class ReportApiTest(unittest.TestCase):
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

    def _generate(self, **body):
        return self.client.post("/api/v1/reports/generate", headers=self.headers, json=body)

    def test_generate_is_idempotent(self) -> None:
        """Same period twice must refresh the row, never stack a duplicate."""
        period = "2026-03-04"
        body = {"type": "DAILY", "period_start": period, "period_end": period}

        first = self._generate(**body)
        self.assertIn(first.status_code, (200, 201), first.text)
        second = self._generate(**body)
        self.assertEqual(second.status_code, 200, second.text)

        self.assertEqual(
            first.json()["data"]["id"],
            second.json()["data"]["id"],
            "regenerating the same period must update in place",
        )

        listed = self.client.get("/api/v1/reports?type=DAILY", headers=self.headers).json()["data"]
        matching = [
            row
            for row in listed
            if row["period_start"] == period and row["period_end"] == period and row["dimension"] == DIMENSION_ALL
        ]
        self.assertEqual(len(matching), 1, f"expected exactly one row, got {matching}")

    def test_empty_period_generates_without_error(self) -> None:
        """A period with no journals is still a valid report."""
        period = "2020-01-01"
        response = self._generate(type="DAILY", period_start=period, period_end=period)
        self.assertIn(response.status_code, (200, 201), response.text)

        data = response.json()["data"]
        self.assertEqual(data["content"]["journal_count"], 0)
        self.assertEqual(data["content"]["active_days"], 0)
        self.assertEqual(data["content"]["highlights"], [])
        # The template must still produce a readable sentence.
        self.assertIn("没有新的日志记录", data["summary"])

    def test_summary_and_title_are_populated(self) -> None:
        period = "2026-03-05"
        data = self._generate(type="DAILY", period_start=period, period_end=period).json()["data"]
        self.assertTrue(data["summary"])
        self.assertIn(period, data["title"])
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["content"]["period"]["start"], period)
        self.assertEqual(data["content"]["period"]["end"], period)
        self.assertEqual(data["content"]["period"]["days"], 1)

    def test_dimension_scopes_the_aggregation(self) -> None:
        today = _utc_today().isoformat()
        self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": "维度测试：今天推进了工作项 alpha。", "category": "WORK"},
        )
        self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": "维度测试：今天读了学习材料 beta。", "category": "LEARNING"},
        )

        data = self._generate(
            type="DAILY", period_start=today, period_end=today, dimension="WORK"
        ).json()["data"]
        self.assertEqual(data["dimension"], "WORK")
        self.assertEqual(
            set(data["content"]["category_breakdown"]),
            {"WORK"},
            "a scoped report must only count journals in that domain",
        )

    def test_touched_todos_replace_goals_in_the_content(self) -> None:
        """§D8: the content contract names todos and carries no progress."""
        today = _utc_today().isoformat()
        title = "报告待办探针"
        self.client.post("/api/v1/todos", headers=self.headers, json={"title": title, "category": "WORK"})
        self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": f"今天推进了{title}这件事。", "category": "WORK"},
        )

        data = self._generate(type="DAILY", period_start=today, period_end=today).json()["data"]
        self.assertIn("todos", data["content"])
        self.assertNotIn("goals", data["content"], "the goals key was renamed, not duplicated")
        self.assertIn(title, [item["title"] for item in data["content"]["todos"]])
        for item in data["content"]["todos"]:
            self.assertIn("completed", item)
            self.assertNotIn("progress", item)

    def test_unknown_type_is_rejected(self) -> None:
        self.assertEqual(self._generate(type="NOPE").status_code, 422)

    def test_known_but_unsupported_type_is_rejected(self) -> None:
        """QUARTERLY is a valid ReportType but the engine cannot aggregate it."""
        self.assertEqual(self._generate(type="QUARTERLY").status_code, 422)

    def test_missing_report_returns_404(self) -> None:
        response = self.client.get("/api/v1/reports/does-not-exist", headers=self.headers)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"]["code"], "REPORT_NOT_FOUND")

    def test_delete_removes_the_report(self) -> None:
        period = "2026-03-06"
        report_id = self._generate(type="DAILY", period_start=period, period_end=period).json()["data"]["id"]

        deleted = self.client.delete(f"/api/v1/reports/{report_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(
            self.client.get(f"/api/v1/reports/{report_id}", headers=self.headers).status_code,
            404,
        )

    def test_list_filters_by_type(self) -> None:
        weekly = self._generate(
            type="WEEKLY", period_start="2026-03-02", period_end="2026-03-08"
        ).json()["data"]
        listed = self.client.get("/api/v1/reports?type=WEEKLY", headers=self.headers).json()["data"]
        self.assertTrue(listed)
        self.assertTrue(all(row["type"] == "WEEKLY" for row in listed), listed)
        self.assertIn(weekly["id"], [row["id"] for row in listed])

    def test_job_targets_the_period_that_just_ended(self) -> None:
        """The cron runs just after midnight, so it must cover the day before."""
        from app.core.database import SessionLocal
        from app.jobs.handlers import ReportGenerationJob

        async def run() -> dict:
            async with SessionLocal() as session:
                result = await ReportGenerationJob().run(session, self.user_id, {"report_type": "DAILY"})
                await session.commit()
                return result

        result = asyncio.run(run())
        yesterday = (_utc_today() - timedelta(days=1)).isoformat()
        self.assertEqual(result["period_start"], yesterday)
        self.assertEqual(result["period_end"], yesterday)
        self.assertEqual(result["type"], "DAILY")

    def test_job_skips_an_unsupported_type(self) -> None:
        from app.core.database import SessionLocal
        from app.jobs.handlers import ReportGenerationJob

        async def run() -> dict:
            async with SessionLocal() as session:
                return await ReportGenerationJob().run(session, self.user_id, {"report_type": "YEARLY"})

        self.assertIn("skipped", asyncio.run(run()))

    def test_job_honours_the_weekly_toggle(self) -> None:
        """``weekly_report_enabled`` must gate the weekly cron."""
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.jobs.handlers import ReportGenerationJob
        from app.models.user import UserSetting

        async def flip(enabled: bool) -> None:
            async with SessionLocal() as session:
                setting = await session.scalar(select(UserSetting).where(UserSetting.user_id == self.user_id))
                if setting is not None:
                    setting.weekly_report_enabled = enabled
                    await session.commit()

        async def run() -> dict:
            async with SessionLocal() as session:
                return await ReportGenerationJob().run(session, self.user_id, {"report_type": "WEEKLY"})

        try:
            asyncio.run(flip(False))
            self.assertIn("skipped", asyncio.run(run()))
        finally:
            asyncio.run(flip(True))
        # Restored: the job runs again.
        self.assertNotIn("skipped", asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
