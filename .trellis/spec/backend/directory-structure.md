# Directory Structure

> How backend code is organized in this project.

---

## Overview

The backend is a layered FastAPI application. Dependencies point **inward**: API
routers depend on services, services depend on repositories and models. A lower
layer never imports an upper one.

```
api/  ──►  services/  ──►  repositories/  ──►  models/
  │            │
  └────────────┴──►  schemas/  (Pydantic contracts, no dependencies)

ai/  ──►  services/, repositories/, models/     jobs/ ──►  services/, ai/, models/
```

---

## Directory Layout

```
backend/
├── app/
│   ├── main.py                 FastAPI app, lifespan, router registration
│   ├── ai/                     AI layer (own sub-packages, see below)
│   │   ├── agents/base.py      BaseAgent + 7 agents + AgentRegistry
│   │   ├── gateway/            base, mock_gateway, openai_gateway, model_router
│   │   ├── rag/runtime.py      RAGRuntime (hybrid retrieval)
│   │   ├── runtime/            base (context/input/result), runtime (loop)
│   │   ├── tools/              registry (definitions + execution), proposals
│   │   └── context.py          ContextRuntime
│   ├── api/
│   │   ├── deps.py             get_current_user and other dependencies
│   │   └── v1/                 One router per resource + responses.py helper
│   ├── core/
│   │   ├── config.py           Pydantic Settings (all env vars)
│   │   ├── database.py         Engine, SessionLocal, get_db, custom column types
│   │   ├── errors.py           ErrorCode enum + AppError hierarchy
│   │   ├── logging.py          structlog configuration
│   │   └── security.py         Password hashing, JWT
│   ├── infrastructure/bus/     EventBus + RedisEventBus, event_bus singleton
│   ├── jobs/                   handlers, in_process dispatcher, arq worker
│   ├── models/                 SQLAlchemy models (21 tables)
│   ├── repositories/           Query-level data access per aggregate
│   ├── schemas/common.py       All request/response Pydantic models
│   └── services/               Domain logic + report_engine, insight_engine
├── migrations/                 Alembic (env.py, versions/)
├── tests/                      unittest suites + _env.py bootstrap
├── alembic.ini
└── requirements.txt
```

---

## Module Organization

- **API routers are thin.** They validate input via Pydantic, call one service
  method, and wrap the result with `ok(request, ...)`. No business logic, no
  direct ORM queries.
- **Services own domain rules.** They orchestrate repositories, publish events,
  and are the unit that the AI layer and jobs call.
- **Repositories own queries.** One per aggregate; the only place SQLAlchemy
  `select()` statements for that aggregate are written.
- **Engines are services.** `report_engine.py` and `insight_engine.py` produce
  derived domain output and are called by both routers and jobs.
- **Cross-cutting concerns live in `core/`.** Config, DB wiring, errors, logging,
  security — never in a router or service.

**Adding an endpoint:** schema in `schemas/common.py` → repository method if new
queries are needed → service method → router in `api/v1/` registered in `main.py`.

---

## Naming Conventions

| Kind | Convention | Example |
|---|---|---|
| Module | `snake_case`, singular noun | `insight_engine.py` |
| Router file | singular resource name | `api/v1/goal.py` |
| Service / Repository class | `<Aggregate>Service` / `<Aggregate>Repository` | `GoalService` |
| Pydantic model | `<Entity><Action>` | `EventCreate`, `GoalUpdate` |
| Error code | `SCREAMING_SNAKE` | `TOOL_PERMISSION_DENIED` |
| Event name | PascalCase verb-past | `EventCreated`, `ReportGenerated` |

---

## Examples

- **Clean API layer**: `app/api/v1/goal.py` — validation, one service call, `ok()`.
- **Service with events**: `app/services/event_service.py` — writes, then
  publishes `EventCreated`.
- **Derived logic**: `app/services/report_engine.py` — pure aggregation with a
  fixed output contract.

---

## Related

- [Database Guidelines](./database-guidelines.md)
- [Error Handling](./error-handling.md)
- [Quality Guidelines](./quality-guidelines.md)
