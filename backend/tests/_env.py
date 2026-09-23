"""Shared test environment bootstrap.

Call ``configure()`` at the very top of each test module, before importing
``app.*``. All modules share a single database so discovery order is safe;
the environment is only applied once per process.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

DB_NAME = "personalos_tests.db"


def configure() -> Path:
    db_file = Path(tempfile.gettempdir()) / DB_NAME
    if os.environ.get("_PERSONALOS_TEST_ENV_READY"):
        return db_file

    db_file.unlink(missing_ok=True)
    os.environ["_PERSONALOS_TEST_ENV_READY"] = "1"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    os.environ.setdefault("SEED_DEMO_USER", "true")
    os.environ.setdefault("LLM_PROVIDER", "mock")
    return db_file
