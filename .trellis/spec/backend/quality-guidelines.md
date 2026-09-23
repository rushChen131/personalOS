# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

Quality is enforced by a small, opinionated gate that runs locally and in CI.
Nothing here is aspirational — each rule maps to a command that fails the build.

| Gate | Command | Must pass |
| --- | --- | --- |
| Lint + import order | `ruff check .` | zero findings |
| Format | `ruff format --check .` | no diff |
| Type contract | Pydantic models at every boundary | `extra="forbid"` where input is user-supplied |
| Tests | `python -m unittest discover` (via `make test`) | all pass |
| Compose config | `docker compose config -q` | valid |

`line-length` is **120** and `target-version` is **py312**. Ruff's selected rule
sets are `E, F, W, I, B, DTZ, BLE` (with `B008` ignored globally, since FastAPI
`Depends()` in defaults is idiomatic).

---

## Forbidden Patterns

Each of these is either lint-enforced or has caused a real defect in this
codebase.

### Banned by ruff

| Code | Rule | Why |
| --- | --- | --- |
| `DTZ005` / `DTZ011` | no naive `datetime.now()` / `date.today()` | everything is timezone-aware UTC; `date.today()` reads the *host* timezone |
| `BLE001` | no blanket `except Exception` | swallows bugs; only permitted in declared boundary layers (below) |
| `B008` | function calls in defaults | ignored globally *because* `Depends()` is accepted |
| `F401`/`I001` | unused imports, unsorted imports | blockbusting clutter |

### Boundary-only exemptions

`pyproject.toml` grants per-file ignores, and **only** these paths may catch
broad exceptions:

```toml
"app/api/**"        = ["DTZ005", "BLE001"]
"app/ai/runtime/**" = ["BLE001"]
"app/ai/gateway/**" = ["BLE001"]
"app/jobs/**"       = ["BLE001", "DTZ011"]
"app/infrastructure/**" = ["BLE001"]
"app/models/**"     = ["F821"]
```

The rationale is written in the config itself: *"Boundary layers translate any
provider/plugin failure into a domain error."* If you need `BLE001` somewhere
else, that is a design smell — wrap the call instead.

### Banned by convention

- **`print()` / stdlib `logging`** — use `app.core.logging.logger`.
- **`session.commit()` inside a service** — breaks rollback and job draining.
- **Lazy relationship access** — `MissingGreenlet`; always `selectinload`.
- **`HTTPException` outside the auth dependency** — raise `AppError`.
- **Building SQL with f-strings.**
- **Time-independent code comparing naive and aware datetimes.**
- **Catching an exception to return `None`** instead of raising a domain error.
- **`# type: ignore` without an inline reason.**
- **God services** — if a service exceeds ~300 lines, split by aggregate or
  extract an engine.
- **Circular imports worked around with local imports** as a first resort. Fix
  the dependency direction; the `ai/runtime/__init__.py` `__getattr__` lazy
  export exists specifically to break a cycle and is the *documented* exception,
  not a pattern to copy.

---

## Required Patterns

- **Dependency direction is inward**: `api → services → repositories → models`.
  `ai/` and `jobs/` sit beside `services/` and may depend on it, never the
  reverse. Importing an `api.v1` module from a service is a review blocker.
- **Every external value is validated by a Pydantic model** at the router
  boundary — never trust a raw `dict` from the request.
- **All ids are `str`.** Use `UUIDType` for the column; never leak `uuid.UUID`.
- **All timestamps are timezone-aware UTC.** Persist `*_tz`-aware; format for
  display in the frontend only.
- **Success responses go through `ok(request, data)`**; errors are raised as
  `AppError`. Handlers never hand-roll the envelope.
- **`async def` all the way down** for I/O. Never call a blocking SDK inside an
  async path without `run_in_executor` — it stalls the event loop for every
  concurrent request.
- **Public functions have a one-line docstring** if their contract is not obvious
  from the signature.
- **New configuration is a `Settings` field** in `core/config.py` with a sane
  default — never `os.environ[...]` at call sites.
- **Type hints on every function signature.** The codebase targets py312; use
  `X | None`, built-in generics, and `from __future__ import annotations`.

---

## Testing Requirements

Tests live in `backend/tests/` and use the stdlib `unittest` runner, executed via
`make test` (`python -m unittest discover -s tests`).

### Bootstrap

Every test module imports `configure()` from `tests/_env.py` **first**:

```python
from tests._env import configure
configure()
```

`_env.py` points `DATABASE_URL` at a dedicated test SQLite file and installs
settings **once per process** (guarded by `_PERSONALOS_TEST_ENV_READY`).
`app.core.database` builds the engine at import time, so configuring late or
per-module causes "no such table" failures from a stale DB path. This is not
optional ceremony — it was the fix for a real cross-module DB collision.

### What must be covered

| Area | Expectation |
| --- | --- |
| Smoke (`test_smoke.py`) | app boots, health, auth, one CRUD round-trip per core resource |
| AI layer (`test_ai_layer.py`) | agent selection, tool permission enforcement, bounded loop (≤3 rounds), mock gateway determinism, RAG retrieval ordering, SSE event ordering |
| Jobs layer (`test_jobs_layer.py`) | dispatcher drain ordering, handler registration, report/insight engine output contract, idempotency of duplicate insights |
| Endpoint smoke (`scripts/smoke_test.py`, `make smoke`) | full HTTP surface incl. 404 paths, envelope shape, SSE stream, report content contract — 37 checks |
| Bug fixes | a regression test that fails before the fix. Non-negotiable. |

### Standards

- **Determinism is required.** The mock LLM gateway exists so tests never hit a
  network. Tests must not depend on wall-clock time or ordering that the DB does
  not guarantee.
- **Prefer the in-process dispatcher** over the arq worker in tests.
- **Every new branch deserves a test**; a PR that changes behaviour without a
  test change needs a justification in the description.
- Aim to keep the full suite under ~30s locally; it is a gate, not a nightly.

---

## Code Review Checklist

Reviewers should be able to answer **yes** to each:

**Layering**
- [ ] Dependencies point inward; no lower layer imports an upper one.
- [ ] Router is thin: validate → one service call → `ok()`.
- [ ] Queries for an aggregate live in its repository.

**Correctness**
- [ ] Every relationship read after the session boundary is `selectinload`ed.
- [ ] No follow-up job runs before commit; `drain_and_run()` stays after `commit()`.
- [ ] Ids are `str`; timestamps are aware UTC.
- [ ] Errors raise `AppError`/`NotFoundError`, never `HTTPException` or `None`.

**Contract**
- [ ] New `ErrorCode` members are additive, not repurposed.
- [ ] Response schemas are in `schemas/common.py` and used by the router.
- [ ] SSE changes preserve event order: `start → thinking → (tool_call → tool_result)* → content → done`.

**Quality**
- [ ] `ruff check .` and `ruff format --check .` are clean.
- [ ] New behaviour has a test; bug fixes have a regression test.
- [ ] No secrets or user content in logs; ids and lengths only.
- [ ] No new `BLE001`/`DTZ` exemptions outside the boundary paths.

**Docs**
- [ ] A new env var is in `Settings` **and** `.env.example`.
- [ ] A schema/endpoint change updates the relevant spec under `.trellis/spec/`.
