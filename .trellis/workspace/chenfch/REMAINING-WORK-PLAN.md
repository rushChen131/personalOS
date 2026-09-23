# PersonalOS V1.2 — Remaining Work Plan

> Generated after backend-core smoke test (2026-09-21). Smoke: server boots, auth/bootstrap + JWT
> flows work, journal/goal/event/memory create work, timeline/stats aggregate correctly, unified
> `{success, data, request_id}` envelope confirmed, ruff clean. Below is what remains.

## A. backend-core (current task, in_progress)

### A1. Fixed during smoke (done)
- `UUIDType` now normalizes PK to `str(uuid4)` in Python for BOTH dialects (PG native UUID column, SQLite CHAR(32)). Fixes pydantic validation error on `UserResponse.id`.
- Event create defaults `start_time` to now + derives `end_time` from `duration_minutes` (so stats/timeline include manual events).
- Stats by_day/by_week buckets now carry `by_project` (schema `StatsTimeSlice` requires it).
- Heart: `bcrypt` pinned to `>=4.0,<4.1` in requirements.txt (passlib 1.7.4 incompatible with bcrypt 5.x).
- Added `backend/pyproject.toml` ruff config: line-length 120, B008 allowed (FastAPI Depends/Query), per-file ignores (models F821 forward refs, api DTZ005, main B008).

### A2. Verify remaining endpoints (quick, do before commit)
- `GET /auth/me` (needs token)
- `GET /journals/{id}`, `DELETE /journals/{id}`
- `GET /events`, `GET /events/{id}` (detail w/ goals+tags)
- `GET /goals/{id}`, `PUT /goals/{id}`, `DELETE /goals/{id}`, `POST /goals/{id}/metrics`
- `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PUT /projects/{id}`
- `GET /memories`, `GET /memories/{id}`
- `POST /reports/generate`, `GET /reports/{id}`
- `POST /chat/conversations`, `GET /chat/conversations`, `GET /chat/conversations/{id}` (501 / via chat.py — confirm conversation lifecycle works without AI)
- `POST /login`, `GET /insights`

### A3. Add Alembic (missing, in backend-core scope)
- Alembic installed but NO `backend/alembic.ini`, NO `migrations/env.py`, no revisions yet.
- Create `alembic.ini` + `backend/migrations/` with async env.py (asyncio + aiosqlite default, asyncpg for PG).
- Autogenerate initial migration for all tables (verify 21 tables + indexes/constraints) and run `alembic upgrade head` against sqlite.
- Decide: `create_all` stays for dev bootstrap OR migrate to scriptable migrations. Recommend: keep lifespan `create_all` for demo, add migration path for prod PG.

### A4. Persist a smoke script (optional but useful)
- Convert the ad-hoc smoke sequence into `backend/scripts/smoke_test.py` (httpx against running uvicorn, or TestClient in-process). Skip if Tests area is better covered later.

## B. backend-ai (next task — 09-21-backend-ai)
- [ ] ModelGateway: real (openai) + Mock providers; config pick via env `LLM_PROVIDER=mock|openai`
- [ ] AgentRuntime: agent definitions (7 agents: planner, extractor, memory-refiner, insight-engine, report-generator, chat-composer, context-manager per design2.md)
- [ ] ToolRegistry + tools (get-context, memory-search, journal/create, event/create, goal/progress, insight/create, report/generate)
- [ ] RAG: embed events/journals/memories, vector search (store embedding in existing `embedding: VectorType(1536)` columns) — behind the Mock provider, fall back to keyword/BM25 so search returns hits without keys
- [ ] Wake `/api/v1/chat` (currently returns 501): stream SSE start→thinking→(tool)→content→done
- [ ] Insight generation + report auto-generation wiring
- [ ] Conversation persistence already in schema; hook messages/agent_runs/tool_runs
- [ ] Mock AI responses must be deterministic JSON following the same shapes as real provider (design.md D2)

## C. backend-jobs
- [ ] Job system (jobs table exists): arq worker + redis optional; SQLite fallback demo scheduler
- [ ] Scheduled tasks: insights daily, report daily/weekly queue, memory compaction

## D. frontend
- [ ] Next.js app (per .trellis/spec/frontend + frontend/index.md spec) talking to backend on :8000
- [ ] Timeline/stats dashboards, journal editor, memory search, chat view, goal/project pages

## E. infra-docs
- [ ] .trellis/spec/backend/*.md + frontend/*.md "To be filled" templates → fill with real contracts (models, envelope, SSE protocol, errors, ports)
- [ ] Top-level README run instructions (SQLite default: `uvicorn app.main:app` + `npm run dev`), PG/Redis optional flags

## F. Phase 3 finish (after all children verified)
- [ ] trellis-check full pass on each child
- [ ] trellis-update-spec (write learned contracts into spec files)
- [ ] Commit each child task per .trellis workflow Phase 3.4
- [ ] Parent integration review + archive (via /trellis:finish-work)