"""File logging: the rotating handler and the structlog mirror processor.

``LOG_FILE`` mirrors stdout into a rotating file. The wiring is unusual — the
handler is fed by a processor sitting *after* ``JSONRenderer`` rather than by
routing structlog through stdlib — so these tests pin down the parts that are
easy to break silently.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests._env import configure

configure()

from app.core import logging as app_logging  # noqa: E402
from app.core.config import settings  # noqa: E402


class LogFileTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Deliberately nested: opening the handler must create the parent dir.
        self.path = Path(tmp.name) / "nested" / "backend.log"
        self._originals = {
            key: getattr(settings, key)
            for key in ("log_file", "log_max_bytes", "log_backup_count")
        }
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for key, value in self._originals.items():
            setattr(settings, key, value)

    def _handler(self, **overrides) -> logging.Handler:
        settings.log_file = str(self.path)
        settings.log_max_bytes = overrides.get("max_bytes", 10 * 1024 * 1024)
        settings.log_backup_count = overrides.get("backup_count", 5)
        handler = app_logging._build_file_handler()
        self.assertIsNotNone(handler)
        self.addCleanup(handler.close)
        return handler

    def test_disabled_when_log_file_is_empty(self) -> None:
        """An empty LOG_FILE keeps stdout-only behaviour.

        The test bootstrap relies on this so the suite writes no log files.
        """
        settings.log_file = ""
        self.assertIsNone(app_logging._build_file_handler())

    def test_creates_parent_directory_and_opens_an_empty_file(self) -> None:
        """RotatingFileHandler opens its stream eagerly in ``__init__``.

        So the file appears the moment the app starts, before a single line is
        logged — and stays empty until something is emitted.
        """
        self._handler()
        self.assertTrue(self.path.parent.is_dir(), "parent directory must be created")
        self.assertTrue(self.path.exists(), "the handler opens its stream on construction")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "", "nothing logged yet")

    def test_rotates_and_keeps_the_configured_number_of_backups(self) -> None:
        handler = self._handler(max_bytes=300, backup_count=2)
        for _ in range(30):
            handler.emit(logging.LogRecord("t", logging.INFO, "", 0, "x" * 80, None, None))

        self.assertTrue(self.path.exists())
        # Two backups beside the current file — no third.
        self.assertTrue(Path(f"{self.path}.1").exists())
        self.assertTrue(Path(f"{self.path}.2").exists())
        self.assertFalse(Path(f"{self.path}.3").exists(), "backupCount must be honoured")

    def test_mirror_writes_the_rendered_line_as_parseable_json(self) -> None:
        """The file receives the exact line stdout gets, still valid JSON.

        This is what ``%(message)s`` buys: the processor hands over a rendered
        string, so the file cannot drift from the console.
        """
        handler = self._handler()
        with patch.object(app_logging, "_file_handler", handler):
            app_logging.logger.info("mirror.probe", marker="hello")

        content = self.path.read_text(encoding="utf-8").strip()
        self.assertTrue(content, "the mirror must have written something")
        payload = json.loads(content)  # must not be mangled by the formatter
        self.assertEqual(payload["event"], "mirror.probe")
        self.assertEqual(payload["marker"], "hello")
        self.assertEqual(payload["level"], "info")

    def test_mirror_is_a_no_op_when_file_logging_is_off(self) -> None:
        with patch.object(app_logging, "_file_handler", None):
            app_logging.logger.info("mirror.disabled")
        self.assertFalse(self.path.exists())

    def test_uvicorn_error_is_not_attached(self) -> None:
        """``uvicorn.error`` propagates into ``uvicorn``.

        Attaching the file handler to both wrote every startup line twice
        (``Started server process``, ``Application startup complete``, ...), so
        only the two ``propagate=False`` chain roots may be used.
        """
        self.assertEqual(set(app_logging._UVICORN_LOGGERS), {"uvicorn", "uvicorn.access"})
        self.assertNotIn("uvicorn.error", app_logging._UVICORN_LOGGERS)


if __name__ == "__main__":
    unittest.main()
