# Error Handling

> How errors are handled in this project.

---

## Overview

PersonalOS uses a **single error taxonomy + a single wire format**. Every failure
that reaches the HTTP boundary is normalised by one of four exception handlers
into the same envelope shape:

```json
{
  "success": false,
  "error": { "code": "GOAL_NOT_FOUND", "message": "Goal 3f9... does not exist" },
  "request_id": "req_a1b2c3d4e5f6"
}
```

Three rules hold everywhere:

1. **Domain errors are raised as `AppError`**, never as bare `Exception` or
   `HTTPException`. Only auth (via `OAuth2PasswordBearer`) and framework-level
   validation produce non-`AppError` errors, and those are mapped centrally.
2. **Handlers do not build error responses by hand.** They raise; the exception
   handler formats. This is what keeps `code` / `message` / `request_id`
   consistent across every endpoint.
3. **The success path never shares a model with the error path.** Success is
   `{"success": true, "data": ..., "request_id": ...}`; errors carry `error`
   instead of `data`. See `app/schemas/common.py::ApiResponse` /
   `ApiErrorResponse`.

---

## Error Types

All error types live in `backend/app/core/errors.py`.

### `ErrorCode` — the stable contract

`ErrorCode` is a `str`-valued enum. **These values are part of the public
contract** — the frontend switches on them, so they must not be renamed
casually. Add new members; do not repurpose existing ones.

| Group | Codes |
| --- | --- |
| Auth | `AUTH_UNAUTHORIZED` |
| Generic resource | `RESOURCE_NOT_FOUND`, `VALIDATION_ERROR`, `NOT_IMPLEMENTED`, `INTERNAL_ERROR` |
| Per-resource not-found | `GOAL_NOT_FOUND`, `PROJECT_NOT_FOUND`, `EVENT_NOT_FOUND`, `JOURNAL_NOT_FOUND`, `MEMORY_NOT_FOUND`, `REPORT_NOT_FOUND`, `AGENT_NOT_FOUND`, `TOOL_NOT_FOUND` |
| AI / tools | `TOOL_PERMISSION_DENIED`, `AGENT_EXECUTION_FAILED`, `LLM_ERROR`, `VECTOR_SEARCH_ERROR` |

### `AppError` — the base class

```python
class AppError(Exception):
    def __init__(self, code: ErrorCode, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
```

`status_code` defaults to `400`; the handler writes it to the HTTP response
verbatim. Raise subclasses (or `AppError` with an explicit status) rather than
inventing new exception hierarchies.

### Subclasses

| Class | Status | Code | Use |
| --- | --- | --- | --- |
| `NotFoundError` | `404` | caller-supplied | Missing resource: `raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, f"Goal {id} does not exist")` |
| `PermissionDeniedError` | `403` | `TOOL_PERMISSION_DENIED` | Agent attempted a tool outside its granted permission set |

Both are thin convenience wrappers — if you need a different status code,
construct `AppError` directly.

---

## Error Handling Patterns

### Raising, not returning

Services and repositories **raise `AppError`**; they never return `None` to
signal "not found". The API layer does not wrap service calls in
`if result is None: return error(...)`.

```python
# repository
async def get(self, goal_id: str) -> Goal:
    goal = await self.session.get(Goal, goal_id)
    if goal is None:
        raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, f"Goal {goal_id} does not exist")
    return goal
```

### Where each layer stands

| Layer | Responsibility |
| --- | --- |
| `repositories/` | Raise `NotFoundError` for missing rows. Do **not** catch DB errors. |
| `services/` | Enforce domain invariants; raise `AppError`. May translate a low-level exception into a domain code (e.g. vector search failure → `VECTOR_SEARCH_ERROR`). |
| `api/v1/` | Zero `try/except` for the normal path. Just await the service and return `ok(request, data)`. |
| `main.py` | Installs the handlers once via `setup_exception_handlers(app)`. |

### Degradation, not crashes, in the AI layer

AI/agent failures must not take down a request that has already produced useful
output. The runtime catches agent exceptions, emits a `run_error` log, and
continues — surfacing `AGENT_EXECUTION_FAILED` only when nothing usable was
produced. Within the SSE stream, a mid-stream failure is emitted as an
`error` event, not as an aborted connection.

### Never `return error(...)` from a router

`responses.error()` builds the *body* only — it is a plain `dict`, so FastAPI
serialises it with **HTTP 200**. A router that does
`if x is None: return error(request, ...)` therefore ships `404` semantics over
a `200` status, which breaks every client that branches on `response.ok`.

Routers must **raise** instead, and let the central handler attach the status:

```python
# wrong — status is 200
if goal is None:
    return error(request, ErrorCode.GOAL_NOT_FOUND.value, "Goal not found")

# right — status is 404, body identical
if goal is None:
    raise NotFoundError(ErrorCode.GOAL_NOT_FOUND, "Goal not found")
```

`error()` remains public only for the exception handlers themselves and for the
rare streamed case where headers are already committed.

### Malformed ids resolve to 404, not 500

Path params are `str`, and clients can send anything (`/journals/nope`).
`UUIDType.process_bind_param` tolerates a non-UUID string by binding the nil
UUID, so the query is valid, matches no row, and the service raises
`NotFoundError` — a clean `404`. Never let a malformed id reach
`uuid.UUID(...)` unprotected; it becomes an unhandled `ValueError` → `500`.

### `raise ... from`

When translating an exception, preserve the cause:

```python
try:
    await self.vector_store.search(query)
except VectorStoreError as exc:
    raise AppError(ErrorCode.VECTOR_SEARCH_ERROR, str(exc), 502) from exc
```

---

## API Error Responses

### Handlers (registered in `app/api/v1/responses.py`)

| Handler | Catches | Status | Code |
| --- | --- | --- | --- |
| `app_error_handler` | `AppError` | `exc.status_code` | `exc.code.value` |
| `validation_error_handler` | `RequestValidationError` | `422` | `VALIDATION_ERROR` (message = `str(exc.errors())`) |
| `send_500_handler` | `Exception` (catch-all) | `500` | `INTERNAL_ERROR` |
| HTTP exceptions | `HTTPException` | `exc.status_code` | `AUTH_UNAUTHORIZED` if 401, else `INTERNAL_ERROR` |

Note: `RequestValidationError` is a subclass of `Exception`, and `AppError` is
registered before the catch-all — ordering in `setup_exception_handlers` matters
when adding new handlers.

### Request ID

`request_id_middleware` in `main.py` assigns
`request.state.request_id = f"req_{uuid4().hex[:12]}"` on every request **before**
routing. `responses._request_id()` reads it and falls back to generating a fresh
one if the state is missing (e.g. an error raised outside the ASGI middleware
chain). Both the success and error envelopes always carry the same
`request_id`, which is what makes a client-side error report traceable.

### Success envelope

```python
def ok(request: Request, data: Any = None) -> dict:
    return {"success": True, "data": data, "request_id": _request_id(request)}
```

Usage in a handler:

```python
@router.get("/{goal_id}")
async def get_goal(goal_id: str, request: Request, session: AsyncSession = Depends(get_db)):
    goal = await goal_service.get(session, goal_id)
    return ok(request, GoalResponse.model_validate(goal))
```

### The chat endpoint is the one exception

`POST /api/v1/chat` returns `text/event-stream`, not JSON. Errors that occur
**before** the stream opens use the normal JSON envelope; errors **after** the
first byte has been written are delivered as an SSE `error` event followed by
stream close (HTTP status is already committed). See the SSE protocol section in
`frontend/type-safety.md`.

---

## Common Mistakes

- **Raising `HTTPException` in a service.** It couples the domain to FastAPI and
  bypasses the `AppError` envelope. Raise `AppError`; only the auth dependency
  should raise `HTTPException`.
- **Returning `None` for a missing row** and letting the API layer 500 on
  attribute access. Raise `NotFoundError` at the repository boundary.
- **Catching `Exception` in a handler** to build a custom error body. It defeats
  the central handler and drops `request_id`.
- **Reusing a generic code** (`RESOURCE_NOT_FOUND`) where a specific one exists.
  The frontend uses these to pick copy and actions.
- **Forgetting `from exc`** when translating, which loses the original traceback
  in logs.
- **Logging the raw exception to the client.** `send_500_handler` currently
  puts `str(exc)` in `message` for local debuggability — do not rely on this in
  production; treat `INTERNAL_ERROR` messages as opaque.
- **Adding an exception handler after the catch-all** — it will never fire.
- **`return error(...)` in a router.** It yields HTTP 200 with an error body.
  Raise `NotFoundError` / `AppError` instead. (This shipped in 13 places across
  9 routers and was fixed on 2026-09-21.)
- **Trusting a path param to be a well-formed UUID.** Validate-by-tolerance in
  `UUIDType`, so `/resource/garbage` is a 404 rather than a 500.
