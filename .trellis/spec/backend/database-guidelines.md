# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

PersonalOS uses **SQLAlchemy 2.0 async ORM** over **PostgreSQL + pgvector** in
production and **SQLite (aiosqlite)** for local dev and tests. The same model
definitions run on both; dialect differences are isolated behind custom types so
that application code never branches on the backend.

| Concern | Choice |
| --- | --- |
| ORM | SQLAlchemy 2.0, `Mapped[...]` / `mapped_column` declarative style |
| Driver | `asyncpg` (PostgreSQL) / `aiosqlite` (SQLite) |
| Sessions | `async_sessionmaker`, `expire_on_commit=False` |
| Migrations | `create_all` on startup for v1.2; Alembic is the intended path once the schema stabilises |
| Vector store | pgvector in PG; JSON-encoded list in SQLite (keyword fallback) |

All connection setup lives in `backend/app/core/database.py`. No module outside
it may create an engine or session factory.

---

## Query Patterns

### Always async, always parameterised

Use `select()` + `await session.scalars(...)` / `await session.execute(...)`.
Never build SQL with f-strings.

```python
stmt = (
    select(Event)
    .where(Event.user_id == user_id)
    .order_by(Event.start_time.desc())
    .limit(limit)
)
events = list(await session.scalars(stmt))
```

### Eager-load relationships — this is not optional

`expire_on_commit=False` plus async lazy loading is a trap: touching an
unloaded relationship **after** the session closes raises
`MissingGreenlet`. Any path that serialises a relationship must eager-load it
with `selectinload` (preferred for collections) or `joinedload` (1:1).

```python
stmt = select(Event).options(selectinload(Event.goals), selectinload(Event.tags))
```

This bit the jobs layer specifically: both
`services/_refresh_goal_progress_for_event` and `services/report_engine`,
which read `event.goals` after the handler's session had been detached, needed
`selectinload(Event.goals)` on the originating events query.

**Rule of thumb:** if a field is in a response schema and comes from a
relationship, the query that loads the parent must eager-load it.

### Batch reads

Use `.in_()` for lookups by id list; avoid N+1 loops:

```python
goals = list(await session.scalars(select(Goal).where(Goal.id.in_(goal_ids))))
```

For aggregate counts, prefer a `select(func.count())` over loading rows.

### Transactions and the job-drain hook

`get_db()` owns the unit of work:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        # follow-up jobs queued by event handlers run only after commit
        from app.jobs.in_process import dispatcher
        await dispatcher.drain_and_run()
```

**Why this shape matters:** event handlers (subscribers on the in-process
`EventBus`) do not write directly. They *schedule* follow-up jobs, which are
drained **after** the commit so the new rows are visible to them. Running a job
inside the request's open transaction from a second session is invisible-write
hell — that was a real bug (job wrote 0 memories). Never move
`drain_and_run()` before `commit()`.

Services must not call `session.commit()`. Let the dependency close the unit of
work so rollback-on-error and job draining stay correct.

### Dialect-agnostic custom types

Three custom `TypeDecorator`s in `database.py` keep models portable:

| Type | PostgreSQL | SQLite | Python value |
| --- | --- | --- | --- |
| `UUIDType` | native `UUID` | `Uuid()` → `CHAR(32)` | always `str` (uuid4 hex) |
| `VectorType(dim=1536)` | `pgvector.Vector(1536)` | JSON list | `list[float]` / JSON string on bind |
| `JSONB` | `JSONB` | `JSON` | `dict` / `list` |

**IDs are always Python `str`.** `UUIDType.process_result_value` stringifies on
read regardless of dialect, so nothing downstream should ever see a
`uuid.UUID`. Use `UUIDType` for every primary key and FK — do not use
`String(36)` directly.

`UUIDType.process_bind_param` is deliberately **tolerant of malformed input**: a
non-UUID string (e.g. a bad path segment) binds the nil UUID, so the query stays
valid and matches no row. The service then raises `NotFoundError` → `404`.
Without this, `uuid.UUID("nope")` raises `ValueError` deep inside the DBAPI
layer and the request 500s.

`VectorType` degrades to keyword search on SQLite by design; do not write code
that assumes vector similarity is available.

---

## Migrations

v1.2 bootstraps the schema with `create_all` during `lifespan` (`init_db()` in
`main.py`), and seeds a demo user when `settings.seed_demo_user` is set.

```bash
# local, fresh DB
rm -f backend/personalos.db && make dev
```

Once the schema is frozen, Alembic replaces `create_all`:

1. `alembic revision --autogenerate -m "add x"` — **always review the generated
   file**; autogenerate misses custom types' details and index changes.
2. Verify the `upgrade()` and write a real `downgrade()`.
3. `alembic upgrade head` against a copy of production-ish data before merging.

Rules that apply now and after Alembic lands:

- Never edit a migration that has been applied anywhere. Add a new one.
- Every migration needs a working `downgrade()`.
- Enabling pgvector (`CREATE EXTENSION vector`) is a one-time migration step,
  not something the app does at runtime.

---

## Naming Conventions

| Object | Convention | Example |
| --- | --- | --- |
| Table | plural `snake_case` | `events`, `goal_projects`, `agent_runs` |
| Column | `snake_case` | `start_time`, `duration_minutes` |
| Primary key | `id` | `id` |
| Foreign key | `<entity>_id` | `project_id`, `goal_id`, `user_id` |
| Timestamp | `_at` suffix, `*_tz`-aware | `created_at`, `last_verified_at`, `discovered_at` |
| Date (no time) | `_date` / bare noun | `start_date`, `target_date` |
| Boolean | `is_*` / `has_*` | `is_archived` |
| Association table | `<a>_<b>` alphabetical | `goal_projects` |
| Index | `ix_<table>_<column>` (SQLAlchemy default) | `ix_events_start_time` |
| Enum-valued column | `UPPER_SNAKE` strings | `status = "ACTIVE"` |

Enum-like columns are stored as **strings**, not PG enums, to keep SQLite
compatibility. Validate the allowed set in the Pydantic schema / service layer.

---

## Common Mistakes

- **Lazy-loading after session close** → `MissingGreenlet`. Add
  `selectinload`. Do not "fix" it by widening the session scope.
- **Running a follow-up job before commit** → writes land in a foreign
  transaction and vanish. Keep `drain_and_run()` after `commit()`.
- **Calling `session.commit()` in a service** → breaks the rollback contract and
  job draining.
- **Storing `date.today()`** → use
  `datetime.now(timezone.utc).date()`; `date.today()` is banned by ruff
  (`DTZ011`).
- **Assuming pgvector is present.** SQLite returns JSON lists.
- **Using `String` for ids** instead of `UUIDType`, which desynchronises PG and
  SQLite behaviour.
- **Mutating a relationship list without loading it** — assign
  `obj.goals = [...]` after `selectinload`ing it, never `.append` onto an
  unloaded collection.
- **`echo=True` left on.** `create_async_engine(..., echo=False)` — use structlog
  for query observability instead of dumping SQL.
