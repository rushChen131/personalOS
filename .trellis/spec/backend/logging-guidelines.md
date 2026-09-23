# Logging Guidelines

> How logging is done in this project.

---

## Overview

PersonalOS logs through **structlog** with a JSON renderer. There is exactly one
logger accessor — `from app.core.logging import logger` — configured in
`backend/app/core/logging.py`:

```python
_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.JSONRenderer(),
]
structlog.configure(
    processors=_processors,
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
logger = structlog.get_logger("personalos")
```

Key consequences:

- **Output is JSON, one object per line.** Logs are meant to be shipped and
  queried, not read in a terminal.
- **The floor level is `INFO`.** `logger.debug(...)` calls are compiled out of
  the effective output unless the filter is reconfigured; do not put
  operationally important facts at `debug`.
- **`merge_contextvars` is first**, so anything bound via
  `structlog.contextvars.bind_contextvars(...)` is automatically attached to
  every subsequent log line in that task/request.

Never use the stdlib `logging` module directly, and never `print()`.

---

## Log Levels

| Level | Use for | Examples |
| --- | --- | --- |
| `debug` | High-volume, dev-only detail | per-row loop iterations, raw LLM payloads (redacted), cache hits |
| `info` | Normal lifecycle events worth counting | startup, seed, job started/completed, SSE stream opened, agent run finished |
| `warning` | Recoverable / degraded but expected | LLM gateway fell back to mock, vector store unavailable → keyword search, tool attempt blocked by permission |
| `error` | Operation failed, request still served | agent raised, job failed, LLM call errored after retries |
| `critical` | Process cannot continue | engine unreachable at startup |

Guidance: `exception`/`error` is for *this operation failed*; `warning` is for
*we noticed and degraded*. If you would page someone, it is `error` or above.

---

## Structured Logging

### Event name first, context as kwargs

The first positional argument is a stable, greppable **event name** in
lowercase `snake_case`. Everything else is a keyword argument. Never format
values into the event name.

```python
# good
logger.info("startup", app=settings.app_name, version=settings.app_version,
            db=settings.database_url, llm_provider=settings.llm_provider)
logger.info("seed demo user")
logger.info("agent run finished", run_id=run.id, agent=agent.name, rounds=n, duration_ms=ms)

# bad
logger.info(f"agent {agent.name} finished in {ms}ms")
```

### Required fields for operationally significant events

| Field | Applies to | Source |
| --- | --- | --- |
| `request_id` | anything in an HTTP request | bind it from `request.state.request_id` |
| `run_id` | agent execution, SSE | `AgentRun.id` |
| `job` / `job_id` | job start/finish/failure | dispatcher |
| `agent` | agent selection & tools | agent name |
| `tool` | tool call / denial | tool name |
| `user_id` | user-scoped writes | auth dependency |
| `duration_ms` | anything timed | monotonic delta, integer ms |

### Binding request context

Bind once per request instead of threading `request_id` through every call:

```python
import structlog

structlog.contextvars.bind_contextvars(request_id=request.state.request_id)
try:
    ...
finally:
    structlog.contextvars.clear_contextvars()
```

Because `merge_contextvars` is the first processor, every log emitted inside that
scope carries `request_id` automatically.

### Exceptions

Use `format_exc_info` — pass the exception object, do not stringify it:

```python
try:
    await handler.run(...)
except Exception:
    logger.exception("job failed", job=name, job_id=job_id)
```

`logger.exception` (or `logger.error(..., exc_info=True)`) gives the rendered
traceback. `logger.error("job failed", err=str(exc))` throws away the frames.

---

## What to Log

- **Lifecycle:** startup (config summary), shutdown, DB init, demo seeding.
- **Job execution:** start, finish with `duration_ms`, and failure — one line
  each, keyed by job name/id.
- **Agent execution:** which agent was selected, tool calls (name + success),
  permission denials, round count, termination reason.
- **Model routing:** chosen provider/model per task type, and any fallback to the
  mock gateway (as `warning`).
- **Event-driven side effects:** `EventCreated` → which subscribers ran → which
  follow-up jobs were scheduled and drained.
- **Degradation:** pgvector unavailable → keyword search; Redis unavailable →
  in-process bus. Always `warning`, always with the reason.
- **Security-relevant decisions:** auth failures, permission denials (never the
  credential itself).

---

## What NOT to Log

- **Passwords, password hashes, JWTs, `SECRET_KEY`, API keys.** Redact before
  binding; never pass a token object into a logger.
- **Full user journal / memory content.** Journals and memories are the most
  sensitive data in this app. Log ids and lengths, not bodies. If a body is
  genuinely required for debugging, gate it behind an explicit opt-in flag and
  truncate.
- **Raw LLM prompts/responses** at `info`. They routinely contain user content.
  `debug` only, truncated, and never in production.
- **Embedding vectors.** Log `len(vector)` and `dim`, never the values.
- **Full request/response bodies** for the chat endpoint.
- **Cross-user identifiers** in a user-scoped log line — it makes per-user log
  isolation impossible and leaks relationships between accounts.
- **PII beyond what the event needs.** Prefer `user_id` over email or name.

If you are unsure, log the identifier and the shape (`content_len=482`), not the
payload.
