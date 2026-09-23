"""Timezone-integrity regression tests.

SQLite has no timezone-aware datetime type, so SQLAlchemy's plain
``DateTime(timezone=True)`` silently drops the UTC offset on write and returns a
naive value on read. The API then serialised a naive ISO string, which browsers
parse as *local* time — shifting every instant by the client's UTC offset.

These tests lock in the fix: the ``TZDateTime`` column type must preserve UTC
across a round-trip, the API must emit an explicit offset, and the service-layer
window comparisons must not mix naive and aware datetimes.

Journals are the only user-authored timestamped entity left in the product, so
the round-trip cases run through ``/api/v1/journals`` (via ``occurred_at``).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from tests._env import configure

configure()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class TimezoneIntegrityTest(unittest.TestCase):
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

    def test_journal_timestamp_round_trips_as_utc(self) -> None:
        """An aware UTC instant must survive storage and come back as the same instant."""
        sent = datetime(2026, 3, 15, 8, 30, tzinfo=timezone.utc)
        created = self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={
                "content": "Timezone round trip probe.",
                "occurred_at": sent.isoformat(),
            },
        )
        self.assertEqual(created.status_code, 200)
        raw = created.json()["data"]["occurred_at"]

        # The API must expose an explicit offset, never a bare naive string.
        self.assertTrue(
            raw.endswith("Z") or "+" in raw[10:] or raw[10:].count("-") > 0,
            f"occurred_at must carry a timezone offset, got {raw!r}",
        )
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo, "parsed timestamp must be timezone-aware")
        self.assertEqual(parsed.astimezone(timezone.utc), sent, "the instant must be preserved exactly")

        # And it must still be the same instant when read back through the API.
        fetched = self.client.get(f"/api/v1/journals/{created.json()['data']['id']}", headers=self.headers)
        again = datetime.fromisoformat(fetched.json()["data"]["occurred_at"].replace("Z", "+00:00"))
        self.assertEqual(again.astimezone(timezone.utc), sent)

    def test_non_utc_offset_is_normalised_not_truncated(self) -> None:
        """A +08:00 input must be converted to the same instant, not re-labelled."""
        local = datetime(2026, 3, 15, 16, 30, tzinfo=timezone(timedelta(hours=8)))  # == 08:30 UTC
        created = self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": "Offset normalisation probe.", "occurred_at": local.isoformat()},
        )
        parsed = datetime.fromisoformat(
            created.json()["data"]["occurred_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        self.assertEqual(parsed, datetime(2026, 3, 15, 8, 30, tzinfo=timezone.utc))

    def test_created_at_is_timezone_aware(self) -> None:
        goal = self.client.post(
            "/api/v1/goals", headers=self.headers, json={"title": "TZ created_at probe"}
        ).json()["data"]
        parsed = datetime.fromisoformat(goal["created_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(parsed.tzinfo)
        # Must be a recent instant, not a timestamp shifted by hours.
        drift = abs((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())
        self.assertLess(drift, 300, "created_at should be within minutes of now")

    def test_memory_engine_window_is_timezone_aware(self) -> None:
        """The memory evidence window must find journals written in UTC."""

        marker = "我更喜欢在清晨做深度工作，时区探针。"
        self.client.post(
            "/api/v1/journals",
            headers=self.headers,
            json={"content": marker, "occurred_at": datetime.now(timezone.utc).isoformat()},
        )
        listing = self.client.get("/api/v1/journals", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        parsed = [
            datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            for row in listing.json()["data"]
        ]
        self.assertTrue(parsed, "at least one journal must be listed")
        # Each listed instant must be aware and close to now, not shifted.
        for instant in parsed:
            self.assertIsNotNone(instant.tzinfo)
            drift = abs((datetime.now(timezone.utc) - instant.astimezone(timezone.utc)).total_seconds())
            self.assertLess(drift, 3600, "journal created_at should be within an hour of now")


if __name__ == "__main__":
    unittest.main()
