# backend-core 执行计划

## Step 1. 项目骨架
- `backend/requirements.txt`（fastapi, uvicorn[standard], sqlalchemy, aiosqlite, asyncpg, alembic, pydantic, pydantic-settings, python-jose, passlib[bcrypt], httpx, python-multipart, structlog, pgvector, ruff）
- `backend/app/{main.py, core/, models/, schemas/, repositories/, services/, api/v1/, infrastructure/database/}`
- `backend/alembic.ini` + `migrations/`

## Step 2. 配置 + 数据库
- `core/config.py`：DATABASE_URL 默认 `sqlite+aiosqlite:///./personalos.db`，支持 postgres
- `database.py`：create_async_engine + async_sessionmaker + `get_db` 依赖
- Embedding 列：`models/base.py` 里定义 dialect-aware `Vector` 类型（PG→pgvector.Vector(1536)，SQLite→JSON）

## Step 3. 模型（models/ 每个域一个文件，或按域分组）
- 全部 20 表；UUID 主键（TypeDecorator：PG uuid / SQLite char(32)）；枚举用 str + validate
- 关系：Event↔Goal(secondary event_goals), Event↔Tag, Goal↔Project(goal_projects), Journal→events, Memory→memory_sources(通用 polymorphic source), Report→report_definitions, Conversation→messages→agent_runs→tool_runs

## Step 4. Schemas（pydantic v2，from_attributes）
- 每域 create/update/response；与设计文档字段一致

## Step 5. Repositories
- event_repository: create(+goals/tags), list(filters: user_id,start_time,end_time,type,project_id,limit,offset), get, timeline, stats
- goal_repository, project_repository, journal_repository, memory_repository(含 keyword search), report_repository, insight_repository, conversation_repository

## Step 6. Services
- EventService(create + publish EventCreated via bus), GoalService(progress calc), MemoryService, ReportService(基础统计版), JournalService(触发 bus), ContextService, StatsService

## Step 7. API v1
- router 分文件：auth/journal/event/goal/project/memory/insight/report/chat/context/health
- 统一响应 helper + error handler + request_id middleware
- Chat SSE：`POST /api/v1/chat` 先行返回 `{"success":false,"error":{"code":"NOT_IMPLEMENTED"}}`（backend-ai 接管）；conversations CRUD 完成

## Step 8. 验证
- `cd backend && pip install -r requirements.txt`
- `uvicorn app.main:app` → /docs 检查全部路由
- 写 smoke test 脚本：login→journal→event→timeline→stats→memories/search
- alembic upgrade head 通过
- `ruff check app`