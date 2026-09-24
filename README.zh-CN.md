# PersonalOS

[English](README.md) | **简体中文**

个人生活操作系统：**日志是唯一的人工输入口**，围绕它生长出待办清单、长期记忆、周期报告，以及一个能从你的日常书写中蒸馏出长期事实的 AI 层。

支持两条运行路径：

| 路径 | 依赖服务 | 适用场景 |
|---|---|---|
| **本地（默认）** | SQLite + 进程内事件总线，`LLM_PROVIDER=mock` | 开发调试 —— 不需要 Docker，不需要任何 API Key |
| **完整栈** | PostgreSQL + pgvector、Redis、MinIO、arq worker | 贴近生产的部署形态 |

---

## 快速开始

### 1. 本地运行（不用 Docker，不用 API Key）

后端直接跑在 SQLite 上，自带一个种子演示账号和一个确定性的 mock LLM，因此**整个产品可以完全离线运行**。

```bash
# --- 后端 ---
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS / Linux
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# --- 前端（另开一个终端）---
cd frontend
npm install
npm run dev
```

然后打开：

- 前端 —— <http://localhost:3000>
- API 文档（Swagger）—— <http://localhost:8000/docs>
- 健康检查 —— <http://localhost:8000/api/v1/health>

用种子演示账号登录：

```
demo@personalos.local / demo1234
```

### 2. 完整栈（Docker Compose）

```bash
cp .env.example .env      # 按需调整密钥；需要真实模型时设置 LLM_PROVIDER / OPENAI_API_KEY
docker compose up -d --build
```

包含服务：`postgres`（pgvector）、`redis`、`minio`、`backend`、`worker`、`frontend`。

```bash
docker compose down         # 停止
docker compose down -v      # 停止并删除数据卷
```

---

## 仓库结构

```
personalOS/
├── backend/                    FastAPI 服务
│   ├── app/
│   │   ├── ai/                 Agent 运行时、网关、工具、RAG
│   │   │   ├── agents/         BaseAgent + 6 个 Agent + AgentRegistry
│   │   │   ├── gateway/        LLMGateway、MockGateway、OpenAIGateway、ModelRouter
│   │   │   ├── rag/            RAGRuntime（混合检索）
│   │   │   ├── runtime/        AgentRuntime、AgentContext/Input/Result
│   │   │   ├── tools/          ToolRegistry、权限模型、动作提案
│   │   │   └── context.py      ContextRuntime
│   │   ├── api/v1/             HTTP 路由（薄适配层）
│   │   ├── core/               config、database、security、errors、logging
│   │   ├── infrastructure/bus/ EventBus（进程内）+ RedisEventBus
│   │   ├── jobs/               任务处理器、进程内调度器、arq worker
│   │   ├── models/             SQLAlchemy 模型（21 张表）
│   │   ├── repositories/       数据访问
│   │   ├── schemas/            Pydantic 契约
│   │   └── services/           领域服务 + 记忆抽取器 / 引擎
│   ├── migrations/             Alembic
│   └── tests/                  unittest 测试套件
├── frontend/                   Next.js 15 + Tailwind + Zustand + TanStack Query
│   └── src/
│       ├── app/                App Router 页面
│       ├── components/         共享 UI
│       ├── hooks/              查询 + 会话 hooks
│       ├── lib/                API 客户端、SSE 客户端、格式化工具
│       ├── stores/             Zustand stores
│       └── types/              API 类型
├── docker-compose.yml
├── .env.example
├── Makefile
└── .trellis/                   任务 / 规范管理（见 AGENTS.md）
```

---

## 配置

后端所有配置都来自环境变量（或 `backend/.env`）。完整清单见 `.env.example`，以下是关键项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./personalos.db` | 用 PG 时改为 `postgresql+asyncpg://…` |
| `REDIS_URL` | `redis://localhost:6379/0` | 仅 arq worker / Redis 事件总线需要 |
| `LLM_PROVIDER` | `mock` | `mock`（不需要 Key）或 `openai` |
| `OPENAI_API_KEY` | _（空）_ | `LLM_PROVIDER=openai` 时必填 |
| `SEED_DEMO_USER` | `true` | 种子账号 `demo@personalos.local / demo1234` |
| `SECRET_KEY` | 开发用值 | **对外暴露 API 前务必修改** |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 前端访问的后端地址 |

### Mock LLM 与真实 LLM

`MockGateway` 是确定性、规则式的：它把一句话路由到正确的只读工具，再基于工具结果合成回答。
它返回与 `OpenAIGateway` **完全相同**的 `{content, tool_calls, usage}` 契约，因此 Agent 运行时**永远不会**因为 provider 不同而分叉。切换到真实模型只是改配置：

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

---

## API 概览

基础路径 `/api/v1`。所有 JSON 响应统一信封
`{success, data, request_id}`；错误为 `{success: false, error: {code, message}, request_id}`。

| 模块 | 接口 |
|---|---|
| 认证 | `POST /auth/login`、`GET /auth/me`、`GET /auth/bootstrap` |
| 日志 | `GET/POST /journals`、`GET/DELETE /journals/{id}` |
| 待办 | `GET/POST /todos`、`GET/PUT/DELETE /todos/{id}` |
| 记忆 | `GET /memories`、`GET /memories/{id}`、`POST /memories/search` |
| 报告 | `GET /reports`、`POST /reports/generate`、`GET/DELETE /reports/{id}` |
| 对话 | `POST /chat` **（SSE）**、`GET/POST /chat/conversations`、`GET /chat/conversations/{id}` |
| 动作 | `POST /actions/{id}/confirm` |
| 上下文 | `GET /context` |

`GET /journals`、`GET /todos`、`GET /memories` 均支持 `?category=` 过滤；`/memories/search` 在请求体里接收 `category`。`GET /todos` 还支持 `?completed=true|false`，用来只看已完成或只看未完成。

> **一条待办是清单项，不是进度条。** `POST /todos` 只收 `title` 与 `category`；完成态是一个可空的 `completed_at` 时间戳 —— `null` 表示未完成，有值表示已完成**且该值就是完成时刻**。没有 `status`/`progress` 这一对字段，也就不可能出现「ACTIVE 但 100%」这种自相矛盾的行。`PUT /todos/{id}` 同时是勾选/取消勾选的接口：`{"completed": true}` 由服务端盖上时间戳，`{"completed": false}` 清空它。旧的 `/goals` 路由与 `/goals/{id}/metrics` 入口已删除（`404`）；`todo_metrics` 表保留但不再对外暴露。

> **日志是唯一的人工输入。** `Journal → Candidate → Memory` 流水线直接从日志正文中蒸馏长期事实。`Event`、`Insight`、`Goal` 三个模块已从 API 和 UI 退役：模型与数据表为向后兼容而保留（目标是被**改名**成待办，数据整行搬过去了），但**已不存在任何读写它们的代码路径**。`POST /memories` 随之一并删除 —— 记忆不能手工录入。

> **报告是「算出来的」，不是「写出来的」。** `POST /reports/generate` 把一个周期内的日志折叠成一行 `Report`：篇数、活跃天数、类型与心情分布、本期推进的待办与沉淀的记忆，以及若干条高亮。引擎是**纯聚合**（不调 LLM），所以同一批日志永远算出同一份报告。生成是**幂等**的：同一组 `(type, period_start, period_end, dimension)` 重复请求会返回已有那行，而不是再建一行。`dimension` 用来把报告限定在单个 `Category` 上，不传（或传 `ALL`）表示全生活域。支持的类型是 `DAILY` / `WEEKLY` / `MONTHLY`，其它值一律 `422`。
>
> `period_start` / `period_end` 是显式的 `YYYY-MM-DD` 边界，**日历由调用方决定**：部署环境不保证有 `zoneinfo`，所以服务端只认 UTC 一种日历，绝不猜本地日历；Web 前端自己算真实本地日期再显式传过来。不传边界时服务端取包含今天的那个周期，周以**周一**为起点（ISO）。
>
> 定时任务受 `weekly_report_enabled` / `monthly_report_enabled` 两个用户设置控制。开启后，`daily_report` / `weekly_report` / `monthly_report` 三个 cron 会为**刚刚结束**的那个周期生成报告。用进程内调度器（无 Redis）时跑在 API 进程里；设了 `REDIS_URL` 则由 arq worker 执行。

> **日志、待办、记忆都有「类型」字段**（投资 / 工作 / 学习 …，见 `models/base.py::Category`）。日志与待办的类型由客户端指定；**记忆的类型是继承来的** —— 取它来源日志里占比最高的那个类型，因为记忆从不手工创建。该列为 `NOT NULL` + `server_default='OTHER'`，老客户端不传也不会失败。

### 对话流式协议

`POST /api/v1/chat` 返回 `text/event-stream`（唯一的非 JSON 接口）。事件按以下顺序发出：

```
event: start        data: {"conversation_id": "...", "agent": "journal_agent"}
event: thinking     data: {"agent": "journal_agent"}
event: tool_call    data: {"name": "query_journals", "arguments": {...}}
event: tool_result  data: {"name": "query_journals", "result": {...}}
event: content      data: {"content": "You wrote about Rust three times."}
event: done         data: {"conversation_id": "...", "success": true}
```

`tool_call` / `tool_result` 每次工具调用各重复一次；运行失败时 `error` 会替代 `done`。

---

## AI 层

- **5 个 Agent**（`app/ai/agents/base.py`）：`personal_manager`、`journal_agent`、
  `todo_agent`、`memory_agent`、`coach_agent`。
  每个 Agent 都声明自己的 `tools` 与 `permissions`；注册表按权限过滤工具 schema，越权时返回
  `TOOL_PERMISSION_DENIED`。
- **工具**（`app/ai/tools/registry.py`）：`query_journals`、`query_todos`、
  `search_memory`、`query_reports`、`calendar_tool`（占位）。
- **RAG**（`app/ai/rag/runtime.py`）：在 SQLite/PG 上对记忆与日志做「关键词 + 重要性 + 时效性」混合打分。pgvector 的余弦检索挂在显式开关后面，因此永远不会影响 SQLite 下的结果。
- **动作提案**：高风险工具返回带 `requires_confirmation` 的提案，通过 `POST /actions/{id}/confirm` 确认。
- **链路追踪**：每次运行都会写入 `agent_runs` + `tool_runs`（agent、model、输入、输出、状态、耗时、token）。

## 后台任务

- `app/jobs/handlers.py` —— `MemoryAnalysisJob`、
  `EmbeddingJob`、`MemoryCompactionJob`、`ReportGenerationJob`。
- `app/jobs/in_process.py` —— 本地调度器。把 `JournalCreated` 扇出为「向量化 + 记忆蒸馏」。请求期间入队的任务会在其事务**提交之后**才执行。
- `app/jobs/worker.py` —— arq worker 定义与 cron 排程（记忆压缩：周日 05:00；日报 / 周报 / 月报生成）。
- `app/jobs/worker_main.py` —— 容器入口（`python -m app.jobs.worker`）。

## 引擎

- **MemoryEngine**（`app/services/memory_engine.py`）+ `journal_extractor.py`：
  从日志正文中抽出第一人称陈述，按主体聚桶；只有当某个桶越过 §83 的
  证据数 / 置信度阈值后，才会晋级为一条 `Memory`。
- **ReportEngine**（`app/services/report_engine.py`）：对某个日志窗口做**确定性聚合**，
  产出一行 `Report`。不调 LLM、不含随机性 —— 同一批日志永远算出同一份报告。
  按 `(type, period_start, period_end, dimension)` 幂等，并用模块级 per-user 锁
  保证并发生成收敛到同一行。

> 基于规则的 **InsightEngine** 及其 `GET /insights` 列表已退役：记忆蒸馏本身就在回答
> 「什么在反复出现」，两者功能重叠。`Insight` 模型与 `insights` 数据表为向后兼容而保留。

---

## 开发

```bash
make lint        # ruff（后端）+ next lint（前端）
make test        # 后端 unittest 测试套件
make typecheck   # tsc --noEmit
make migrate     # alembic upgrade head
```

后端测试覆盖核心 API 流程、AI 层（Agent、工具、权限、RAG、SSE 事件顺序）以及任务层（记忆流水线、各引擎、报告）。

## 许可证

私有项目 —— 未授予任何许可。
