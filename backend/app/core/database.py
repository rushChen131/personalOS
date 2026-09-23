from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.types import TypeDecorator, Uuid

from app.core.config import settings


class UUIDType(TypeDecorator):
    """Dialect-aware UUID primary key expressed as a string in Python.

    PostgreSQL -> native UUID column. SQLite -> Uuid() stored as CHAR(32).
    Python-side values are always ``str`` (uuid4 hex) regardless of dialect.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return uuid.UUID(value)
            except ValueError:
                # A malformed id (e.g. an arbitrary path segment like "nope")
                # can never match a real row. Bind the nil UUID so the query
                # stays valid and simply returns nothing; the caller then
                # surfaces the proper 404 instead of a 500.
                return uuid.UUID(int=0)
        return value

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        return str(value)


class TZDateTime(TypeDecorator):
    """Timezone-aware datetime that survives a round-trip on SQLite.

    PostgreSQL stores ``TIMESTAMPTZ`` natively and returns tz-aware values.
    SQLite has no timezone type: SQLAlchemy's plain ``DateTime(timezone=True)``
    *silently discards* the UTC offset on write and returns a naive datetime on
    read. That shift is invisible server-side but very visible in the browser,
    which parses a naive ISO string as *local* time — every timestamp ends up
    off by the client's UTC offset.

    This type normalises on the way in (naive values are assumed UTC, aware
    values are converted to UTC) and re-attaches UTC on the way out, so the
    instant is preserved across both dialects.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            # Naive input is treated as UTC rather than local, so behaviour
            # does not depend on the server's TZ environment variable.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class VectorType(TypeDecorator):
    """Embedding vector column.

    PostgreSQL + pgvector -> pgvector.Vector(1536) with cosine-ops index.
    SQLite (local dev) -> stores the vector as a JSON list so the data model
    stays identical; similarity search degrades to keyword search on those
    environments.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int = 1536):
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(JSON())
        from pgvector.sqlalchemy import Vector as PgVector

        return dialect.type_descriptor(PgVector(self.dim))

    def process_bind_param(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            return json.dumps(value)
        return value

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if dialect.name == "sqlite":
            try:
                return json.loads(value) if isinstance(value, str) else value
            except (TypeError, ValueError):
                return None
        return list(value) if hasattr(value, "__iter__") else value


if settings.database_url.startswith("postgresql"):
    connect_args: dict[str, Any] = {}
    pool_pre_ping = True
else:
    connect_args = {"check_same_thread": False}
    pool_pre_ping = False


class JSONB(JSON):
    """JSON / JSONB dialect agnostic (SQLite: JSON, PG: JSONB)."""

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB as PgJSONB

            return dialect.type_descriptor(PgJSONB())
        return dialect.type_descriptor(JSON())


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=pool_pre_ping,
    connect_args=connect_args,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        # Event handlers queue follow-up jobs while the transaction is open;
        # they are safe to run now that the new rows are visible. Only this
        # request's own queued jobs are drained: the queue is scoped per
        # triggering entity, not shared process-wide.
        from app.jobs.in_process import dispatcher

        await dispatcher.drain_and_run()
