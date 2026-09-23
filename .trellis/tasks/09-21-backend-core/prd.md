# backend-core：数据库 / Repository / Service / API

## Goal
实现 PersonalOS 后端数据与 API 层：全部 SQLAlchemy 模型、Alembic 迁移、Repository 层、Service 层、FastAPI v1 全路由、认证、seed。运行目标为 SQLite 本地可用，PostgreSQL/pgvector 兼容。

## Requirements

### 模型（`技术设计.md` §5-28 全表）
users, user_settings, journals, projects, goals, goal_metrics, events, event_goals, tags, event_tags, goal_projects, memories, memory_sources, insights, reports, report_definitions, conversations, messages, agent_runs, tool_runs, jobs

- 业务主键 UUID，PG 用 `gen_random_uuid()` 默认；SQLite 用 `uuid.uuid4` 默认（方言兼容）
- ENUM：event_type(13), event_source(12), user_status(3) — 用 Python 枚举或在模型层用 String+验证
- embedding VECTOR(1536)：PG 用 pgvector；SQLite 模式中改用 JSON/Text 列（标注注释）
- timestamptz → DateTime(timezone=True)
- 约束：goal.progress 0-100, event.importance/confidence 0-1
- 索引：与设计一致（idx_events_user_time, idx_memories_user_type 等）

### Repository 层（§78 模式）
- 每个领域一个 repo：event/goal/memory/report/journal/project/insight/conversation
- 方法 async，接收 session
- Event: create/list(user_id, time range, type, project)/get/stats/timeline/attach_goals/attach_tags
- Goal: create/list/get/update/with_metrics；GoalProject 关联
- Memory: create/list/search(关键词; 高重要度优先)/get/sources
- Report: create/list/get；ReportDefinition list

### Service 层（§79 模式）
- EventService: create → 存库 + publish EventCreated；stats 聚合；timeline 构建
- JournalService: create → 存 journal + 触发 JournalAgent(经 bus) + embedding 占位
- GoalService: create/update/progress 计算（按关联事件）
- MemoryService: create/search (loop 关键词检索：instr 匹配 content/summary + 元数据 filter + importance 排序)
- ReportService, InsightService, ProjectService, ConversationService
- ContextService: build(page, object_type, object_id) → related_events/projects/memories/reports

### API（§42-45 路由全量）
- /auth: POST /login, GET /me
- /journals: POST, GET, GET /{id}, DELETE /{id}
- /events: POST, GET, GET /{id}, GET /timeline, GET /stats
- /goals: POST, GET, GET /{id}, PUT /{id}, DELETE /{id}, POST /{id}/metrics
- /projects: POST, GET, GET /{id}, PUT /{id}
- /memories: GET, GET /{id}, POST /search
- /insights: GET, GET /{id}
- /reports: POST /generate(可异步), GET, GET /{id}
- /chat: POST（SSE），GET /conversations, GET /conversations/{id}
- /context: GET
- /health
- 统一响应包（success/data/request_id）＋ ErrorCode

### Pydantic Schema（§31-39）
EventCreate/Response, JournalCreate/Response, GoalCreate/Response, MemoryResponse, ReportGenerateRequest/Response, ChatRequest, ContextResponse

### 配置与基础设施
- `app/core/config.py` Settings(pydantic-settings)；database async engine（url 可 sqlite/postgres）；redis 占位（无则内存）
- `app/core/security.py` JWT（python-jose）；`app/main.py` 启动建表+seed dev 用户
- `app/api/v1/*` 全部 router 挂载，prefix /api/v1
- Alembic：alembic.ini + env.py（async SQLite），首个 migration 全表；PG 差异标注

## Acceptance Criteria
- [ ] `pip install -r requirements.txt` 后 `uvicorn app.main:app` 可启动（SQLite）
- [ ] 启动自动 `Base.metadata.create_all` + seed dev 用户 usr_001
- [ ] 全部 20+ 表模型存在，字段/约束/索引与设计一致
- [ ] /health 及全部 v1 路由注册（/docs 可见）
- [ ] 手工 curl：login → 建 journal → 建 event(带 goal/project/tag) → events?start_time&end_time → timeline → stats 均返回正确 JSON
- [ ] memories/search 关键词检索返回结果并按重要度排序
- [ ] events/stats 返回 time distribution 聚合
- [ ] 统一响应格式 success/data/request_id；错误返回 error.code
- [ ] alembic 首个迁移可在 SQLite 执行 upgrade head
- [ ] lint 通过（ruff）+ import 干净

### 上下文（由父任务注入）
- design docs：`技术设计.md`(§5-45, 78-80), `design2.md`(§4-33), `design.md`(§9-20)
- spec：`.trellis/spec/backend/*`

## Notes
- 本任务先锁定数据与 API；AI 相关只留 agent_runs/tool_runs 模型与路由占位，具体 Agent 在 backend-ai 实现
- /chat 路由先返回 501（由 backend-ai 接管），但 conversations/messages 模型与 CRUD 完整
- /reports/generate 先做非 AI 版：聚合统计生成基础 JSON（backend-jobs 再增强）——保证本任务可独立验收