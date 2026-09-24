# PersonalOS

**English** | [简体中文](README.zh-CN.md)

A personal life operating system: journals as the single authored input, with a
todo checklist, long-term memories, periodic reports and an AI layer that
distils durable facts from your daily writing.

Two run paths are supported:

| Path | Services | Best for |
|---|---|---|
| **Local (default)** | SQLite + in-process event bus, `LLM_PROVIDER=mock` | Development — no Docker, no keys |
| **Full stack** | PostgreSQL + pgvector, Redis, MinIO, arq worker | Production-shaped deployment |

---

## Quick start

### 1. Local (no Docker, no API keys)

The backend boots on SQLite with a seeded demo account and a deterministic mock
LLM, so the whole product works offline.

```bash
# --- backend ---
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS / Linux
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# --- frontend (separate terminal) ---
cd frontend
npm install
npm run dev
```

Then open:

- Frontend — <http://localhost:3000>
- API docs (Swagger) — <http://localhost:8000/docs>
- Health — <http://localhost:8000/api/v1/health>

Sign in with the seeded demo account:

```
demo@personalos.local / demo1234
```

### 2. Full stack (Docker Compose)

```bash
cp .env.example .env      # adjust secrets, set LLM_PROVIDER/OPENAI_API_KEY if wanted
docker compose up -d --build
```

Services: `postgres` (pgvector), `redis`, `minio`, `backend`, `worker`, `frontend`.

```bash
docker compose down         # stop
docker compose down -v      # stop and delete volumes
```

---

## Repository layout

```
personalOS/
├── backend/                    FastAPI service
│   ├── app/
│   │   ├── ai/                 Agent runtime, gateways, tools, RAG
│   │   │   ├── agents/         BaseAgent + 6 agents + AgentRegistry
│   │   │   ├── gateway/        LLMGateway, MockGateway, OpenAIGateway, ModelRouter
│   │   │   ├── rag/            RAGRuntime (hybrid retrieval)
│   │   │   ├── runtime/        AgentRuntime, AgentContext/Input/Result
│   │   │   ├── tools/          ToolRegistry, permission model, action proposals
│   │   │   └── context.py      ContextRuntime
│   │   ├── api/v1/             HTTP routers (thin adapters)
│   │   ├── core/               config, database, security, errors, logging
│   │   ├── infrastructure/bus/ EventBus (in-process) + RedisEventBus
│   │   ├── jobs/               Job handlers, in-process dispatcher, arq worker
│   │   ├── models/             SQLAlchemy models (21 tables)
│   │   ├── repositories/       Data access
│   │   ├── schemas/            Pydantic contracts
│   │   └── services/           Domain services + memory extractor/engine
│   ├── migrations/             Alembic
│   └── tests/                  unittest suites
├── frontend/                   Next.js 15 + Tailwind + Zustand + TanStack Query
│   └── src/
│       ├── app/                App Router pages
│       ├── components/         Shared UI
│       ├── hooks/              Query + session hooks
│       ├── lib/                API client, SSE client, formatters
│       ├── stores/             Zustand stores
│       └── types/              API types
├── docker-compose.yml
├── .env.example
├── Makefile
└── .trellis/                   Task/spec management (see AGENTS.md)
```

---

## Configuration

All backend settings come from environment variables (or `backend/.env`). See
`.env.example` for the full list; the important ones:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./personalos.db` | Use `postgresql+asyncpg://…` for PG |
| `REDIS_URL` | `redis://localhost:6379/0` | Only needed for arq worker / Redis bus |
| `LLM_PROVIDER` | `mock` | `mock` (no key) or `openai` |
| `OPENAI_API_KEY` | _(empty)_ | Required when `LLM_PROVIDER=openai` |
| `SEED_DEMO_USER` | `true` | Seeds `demo@personalos.local / demo1234` |
| `SECRET_KEY` | dev value | **Change before exposing the API** |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend origin for the frontend |

### Mock vs. real LLM

`MockGateway` is deterministic and rule-based: it routes an utterance to the right
read tool and synthesises answers from tool results.
It returns the **same** `{content, tool_calls, usage}` contract as
`OpenAIGateway`, so the agent runtime never branches on the provider. Switching to
a real model is a config change only:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

---

## API overview

Base path `/api/v1`. Every JSON response uses the envelope
`{success, data, request_id}`; errors use `{success: false, error: {code, message}, request_id}`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login`, `GET /auth/me`, `GET /auth/bootstrap` |
| Journals | `GET/POST /journals`, `GET/DELETE /journals/{id}` |
| Todos | `GET/POST /todos`, `GET/PUT/DELETE /todos/{id}` |
| Memories | `GET /memories`, `GET /memories/{id}`, `POST /memories/search` |
| Reports | `GET /reports`, `POST /reports/generate`, `GET/DELETE /reports/{id}` |
| Chat | `POST /chat` **(SSE)**, `GET/POST /chat/conversations`, `GET /chat/conversations/{id}` |
| Actions | `POST /actions/{id}/confirm` |
| Context | `GET /context` |

`GET /journals`, `GET /todos` and `GET /memories` all accept a `?category=`
filter; `/memories/search` takes `category` in its body. `GET /todos` also takes
`?completed=true|false` to list only done or only open items.

> **A todo is a checklist item, not a progress bar.** `POST /todos` takes a
> `title` and a `category`; completion is a single nullable `completed_at`
> timestamp — `null` means open, a value means done *and* records when. There is
> no `status`/`progress` pair to disagree with itself. `PUT /todos/{id}` is also
> the check/uncheck call: `{"completed": true}` stamps the timestamp server-side,
> `{"completed": false}` clears it. The old `/goals` route and the
> `/goals/{id}/metrics` entry point are gone (`404`); the `todo_metrics` table is
> retained but no longer exposed.

> **Journals are the only authored input.** The `Journal → Candidate → Memory`
> pipeline distils long-term facts straight out of journal body text. The
> `Event`, `Insight` and `Goal` modules have been retired from the API and UI:
> their models and tables are retained for backward compatibility (goals were
> *renamed* to todos, carrying their rows across), but there is no longer any
> code path that reads or writes them. `POST /memories` was removed with them —
> memories cannot be entered by hand.

> **Reports are generated, never written.** `POST /reports/generate` folds a
> period's journals into one `Report` row: counts, active days, category and
> mood breakdowns, the todos and memories that moved, and a few highlights. The
> engine is pure aggregation — no LLM — so a report is reproducible from the
> journals alone. Generation is **idempotent**: re-requesting the same
> `(type, period_start, period_end, dimension)` returns the existing row rather
> than creating a second one. `dimension` scopes a report to a single
> `Category`; omit it (or send `ALL`) for the whole life. Supported types are
> `DAILY`, `WEEKLY` and `MONTHLY` — anything else is a `422`.
>
> `period_start`/`period_end` are explicit `YYYY-MM-DD` bounds, so the caller
> owns the calendar: `zoneinfo` is not guaranteed to be available on every
> deployment target, so the server treats UTC as its only calendar rather than
> guessing a local one. The web UI computes true local dates and sends them
> explicitly. Omit the bounds and the server uses the period containing today,
> with ISO weeks starting Monday.
>
> The `weekly_report_enabled` / `monthly_report_enabled` user settings gate the
> scheduled jobs. When enabled, `daily_report`, `weekly_report` and
> `monthly_report` crons write the report for the period that just **ended**.
> With the in-process dispatcher (no Redis) they run from the API process; with
> `REDIS_URL` set they run on the arq worker.

> **Every journal, todo and memory carries a life-domain category** (投资 / 工作 /
> 学习 …, see `models/base.py::Category`). Journals and todos take it from the
> client; memories **inherit** the dominant category of the journals they were
> distilled from, because memories are never authored. The column is `NOT NULL`
> with a server default of `OTHER`, so older clients keep working.

### Chat streaming protocol

`POST /api/v1/chat` returns `text/event-stream` (the only non-JSON endpoint).
Events are emitted in this order:

```
event: start        data: {"conversation_id": "...", "agent": "journal_agent"}
event: thinking     data: {"agent": "journal_agent"}
event: tool_call    data: {"name": "query_journals", "arguments": {...}}
event: tool_result  data: {"name": "query_journals", "result": {...}}
event: content      data: {"content": "You wrote about Rust three times."}
event: done         data: {"conversation_id": "...", "success": true}
```

`tool_call`/`tool_result` repeat once per tool invocation; `error` may replace
`done` when a run fails.

---

## AI layer

- **5 agents** (`app/ai/agents/base.py`): `personal_manager`, `journal_agent`,
  `todo_agent`, `memory_agent`, `coach_agent`.
  Each declares `tools` and `permissions`; the registry filters tool schemas by
  permission and returns `TOOL_PERMISSION_DENIED` on violation.
- **Tools** (`app/ai/tools/registry.py`): `query_journals`, `query_todos`,
  `search_memory`, `query_reports`, `calendar_tool` (placeholder).
- **RAG** (`app/ai/rag/runtime.py`): hybrid keyword + importance + recency
  scoring over memories and journals in SQLite/PG. pgvector cosine search is wired
  behind an explicit filter flag so it never affects SQLite results.
- **Action proposals**: high-risk tools return a proposal with
  `requires_confirmation`; confirm via `POST /actions/{id}/confirm`.
- **Tracing**: every run writes `agent_runs` + `tool_runs` (agent, model, input,
  output, status, latency, tokens).

## Background jobs

- `app/jobs/handlers.py` — `MemoryAnalysisJob`, `EmbeddingJob`,
  `MemoryCompactionJob`, `ReportGenerationJob`.
- `app/jobs/in_process.py` — local dispatcher. Wires `JournalCreated → embedding
  + memory distillation`. Jobs queued during a request run **after** its
  transaction commits.
- `app/jobs/worker.py` — arq worker definition with cron schedules (memory
  compaction Sun 05:00, daily/weekly/monthly report generation).
- `app/jobs/worker_main.py` — container entry point (`python -m app.jobs.worker`).

## Engines

- **MemoryEngine** (`app/services/memory_engine.py`) + `journal_extractor.py`:
  pulls first-person statements out of journal body text, buckets them by leading
  entity, and promotes a bucket to a `Memory` only once it clears the §83
  evidence/confidence thresholds.
- **ReportEngine** (`app/services/report_engine.py`): deterministic aggregation
  over a journal window into a `Report` row. No LLM, no randomness — the same
  journals always produce the same report. Idempotent per
  `(type, period_start, period_end, dimension)`, guarded by a module-level
  per-user lock so concurrent generates collapse onto one row.

> The rule-based **InsightEngine** and its `GET /insights` feed were retired:
> memory distillation already answers "what keeps coming up", so the two
> surfaces duplicated each other. The `Insight` model and `insights` table are
> retained for backward compatibility.

---

## Development

```bash
make lint        # ruff (backend) + next lint (frontend)
make test        # backend unittest suites
make typecheck   # tsc --noEmit
make migrate     # alembic upgrade head
```

Backend tests cover the core API flow, the AI layer (agents, tools, permissions,
RAG, SSE ordering) and the jobs layer (memory pipeline, engines, reports).

## License

Private project — no license granted.
