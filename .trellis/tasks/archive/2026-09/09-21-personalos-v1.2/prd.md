# PersonalOS V1.2 完整实现

## Goal

根据设计文档（`design.md`、`design2.md`、`技术设计.md`）实现 PersonalOS 完整 V1.2：
一个个人智能成长与决策系统，核心闭环为 **Journal → Event → Memory → Insight → Goal/Project → Report → AI Chat/Coach → Action**。

用户已确认三项决策：
1. **范围**：全部完整 V1.2（后端全量 + 前端全量 + Agent Runtime + Report Engine + Docker Compose）
2. **基础设施**：本机无 Docker/PG/Redis → **SQLite 本地运行 + PostgreSQL 代码兼容**（pgvector 代码保留为生产部署目标，SQLite 用关键词检索替代向量检索）
3. **AI 策略**：完整 Agent/Tool/RAG/Model Gateway 抽象，配 OpenAI API Key 即可激活；无 Key 时用 Mock 模式保证全链路可跑

## Requirements

### 领域对象（8 个核心）
- User（含 user_settings）
- Journal（原文完整保留，用户"说了什么"）
- Event（事实，用户"发生了什么"，不写入 AI 判断）
- Goal + GoalMetric（目标，一段时间希望达到的状态，可量化）
- Project（执行载体，与 Goal 分开）
- Memory（长期认知，含类型/置信度/来源/有效期）
- Insight（AI 最近发现，含证据/置信度）
- Report（阶段解释，模板可配置 ReportDefinition）

### 后端
- FastAPI + SQLAlchemy 2 async + Pydantic v2
- 数据库模型覆盖设计文档全部表：users, user_settings, journals, events, event_goals, tags, event_tags, goal_projects, goals, goal_metrics, projects, memories, memory_sources, insights, reports, report_definitions, conversations, messages, agent_runs, tool_runs, jobs
- Alembic 迁移（SQLite 本地开发；PostgreSQL 说明文档保留）
- Repository → Service → API 分层，禁止业务 Service 直接写 SQL
- `GET /api/v1/events/stats`、`GET /api/v1/events/timeline`、`POST /api/v1/reports/generate`、`POST /api/v1/memories/search`、`GET /api/v1/context` 等全部 REST 路由
- SSE 流式 Chat（`POST /api/v1/chat`，event: start/thinking/tool_call/tool_result/content/done）
- 统一响应 `{success, data, request_id}` / 错误 `{success, error:{code,message}, request_id}` + Error Code 体系

### AI 层
- AgentRuntime 抽象接口（`run(agent_name, context, input) -> AgentResult`）
- AgentContext（user_id, current_page, current_object, goal_ids, project_ids, memory_ids...）
- BaseAgent：7 个 Agent（personal_manager, journal_agent, goal_agent, memory_agent, insight_agent, report_agent, coach_agent）
- Tool Registry + 权限模型（READ/WRITE/DELETE/EXECUTE）+ 高风险 Tool 需 Action Proposal 用户确认
- Model Gateway + Model Router（按任务选模型：journal_extract→fast, chat→general, insight/report→reasoning, embedding）
- RAG Runtime：Hybrid search（关键词+元数据+时间过滤；SQLite 环境用 FTS/ILIKE 替代向量）
- **Mock 模式**：无 OpenAI key 时规则式抽取/检索，保证无 key 可跑通

### 后台任务
- Event Bus（JournalCreated/EventCreated/...）
- 事件驱动：EventCreated → EmbeddingJob + GoalProgressJob + MemoryAnalysisJob + InsightAnalysisJob
- Background worker（ARQ 或轻量线程/定时器，SQLite 环境不做 Redis 强依赖）

### 前端
- Next.js + TypeScript + Tailwind + shadcn/ui 风格 + Zustand + TanStack Query
- 页面：Dashboard / Journal / Timeline(day/week/month) / Goals(+detail) / Projects(+detail) / Memory / Insights / Reports(+detail) / AI Copilot（全局右侧，上下文感知）/ Settings
- SSE 实时对话（ChatGPT 风格流式输出）
- ECharts 数据可视化（报告/统计）

### 基础设施
- docker-compose.yml（postgres+pgvector, redis, minio, backend, worker, frontend）
- Backend/Frontend Dockerfile、.env.example、README、Makefile

## Constraints

1. SQLite 本地必须可运行、可验证（`uvicorn app.main:app` 直接起）；PostgreSQL/pgvector 差异点用条件/文档标注，不阻塞本地开发
2. 无 OpenAI key 时全链路可用（Mock 模式）
3. 所有 AI 输出结构化（events/memories/insights/actions），不得返回自由文本后就丢弃
4. 所有 AI 行为可追踪：agent_runs + tool_runs 记录模型/输入输出/tokens/延迟/错误
5. AI 是 Copilot 不是主人：不做全自动决定，高风险操作走审批
6. Event = 事实；Memory = 长期认知；Goal = 方向；Project = 执行载体；Insight = AI 发现；Report = 阶段性解释
7. 前端 TypeScript 类型安全；后端 Pydantic schema 与模型解耦

## Acceptance Criteria

- [ ] `backend/` 可 `pip install -r requirements.txt && uvicorn app.main:app` 启动，`/health` 返回 ok
- [ ] 全部 20+ 张表的 SQLAlchemy 模型齐全，Alembic 首个迁移可在 SQLite 生成
- [ ] Journal → POST → (后台/Mock) JournalAgent 抽取 → Event 落库；前端 Journal 页确认流程可用
- [ ] Events stats/timeline 接口返回正确聚合
- [ ] Goals/GoalMetrics/Projects CRUD 可用
- [ ] Memory 检索接口可用（无 key 时关键词检索）
- [ ] Chat SSE 流式输出可用（Mock 模式即可），事件序列 start→…→done
- [ ] Report generate 生成结构化 JSON 报告（Mock 或真实 LLM）
- [ ] Context API 返回 page/object/related_* 上下文
- [ ] 前端 10+ 页面可导航、Dashboard 展示今日多卡
- [ ] AI Copilot 侧栏全局存在，上下文随页面变化
- [ ] agent_runs/tool_runs 每条 AI 执行均落库
- [ ] `docker-compose.yml` + Dockerfile + .env.example + README 就绪
- [ ] 前后端 lint/typecheck 通过

## Task Map

| # | Child | Deliverable |
|---|-------|-------------|
| 1 | 09-21-backend-core | DB models / migrations / repositories / services / FastAPI v1 路由 / auth |
| 2 | 09-21-backend-ai | AgentRuntime / BaseAgent × 7 / ToolRegistry / RAG / ModelGateway |
| 3 | 09-21-backend-jobs | ReportEngine / InsightEngine / EventBus / worker / embedding |
| 4 | 09-21-frontend | Next.js 全页面 / SSE chat / AI copilot / charts |
| 5 | 09-21-infra-docs | docker-compose / Dockerfiles / README / .env.example / Makefile |

依赖顺序：backend-core → backend-ai → backend-jobs（AI/报告依赖 core 的 repository）。frontend 与 infra-docs 依赖出 backend-core 后即可并行。最终集成验收在父任务执行。

## Notes

- 设计文档原文是权威需求来源，本文档为工程化提炼
- `技术设计.md` §102 的 12 步实施顺序作为实现顺序参考：PostgreSQL→Models→Migrations→Repository→Service→FastAPI→AgentRuntime→Tool→RAG→JournalAgent→ReportAgent→Next.js