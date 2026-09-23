# PersonalOS

[English](README.md) | **简体中文**

个人生活操作系统：**日志是唯一的人工输入口**，围绕它生长出目标、长期记忆，以及一个能从你的日常书写中蒸馏事实、并从中提炼洞察的 AI 层。

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
| 目标 | `GET/POST /goals`、`GET/PUT/DELETE /goals/{id}`、`POST /goals/{id}/metrics` |
| 项目 | `GET/POST /projects`、`GET/PUT /projects/{id}` |
| 记忆 | `GET /memories`、`GET /memories/{id}`、`POST /memories/search` |
| 洞察 | `GET /insights` |
| 对话 | `POST /chat` **（SSE）**、`GET/POST /chat/conversations`、`GET /chat/conversations/{id}` |
| 动作 | `POST /actions/{id}/confirm` |
| 上下文 | `GET /context` |

> **日志是唯一的人工输入。** `Journal → Candidate → Memory` 流水线直接从日志正文中蒸馏长期事实，目标进度与洞察分析任务同样读日志。`Event` 与 `Report` 两个模块已从 API 和 UI 退役：模型与数据表为向后兼容而保留，但**已不存在任何读写它们的代码路径**。`POST /memories` 随之一并删除 —— 记忆不能手工录入。

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

- **6 个 Agent**（`app/ai/agents/base.py`）：`personal_manager`、`journal_agent`、
  `goal_agent`、`memory_agent`、`insight_agent`、`coach_agent`。
  每个 Agent 都声明自己的 `tools` 与 `permissions`；注册表按权限过滤工具 schema，越权时返回
  `TOOL_PERMISSION_DENIED`。
- **工具**（`app/ai/tools/registry.py`）：`query_journals`、`query_goals`、
  `search_memory`、`query_insights`、`create_insight`、`calendar_tool`（占位）。
- **RAG**（`app/ai/rag/runtime.py`）：在 SQLite/PG 上对记忆与日志做「关键词 + 重要性 + 时效性」混合打分。pgvector 的余弦检索挂在显式开关后面，因此永远不会影响 SQLite 下的结果。
- **动作提案**：高风险工具返回带 `requires_confirmation` 的提案，通过 `POST /actions/{id}/confirm` 确认。
- **链路追踪**：每次运行都会写入 `agent_runs` + `tool_runs`（agent、model、输入、输出、状态、耗时、token）。

## 后台任务

- `app/jobs/handlers.py` —— `GoalProgressJob`、`MemoryAnalysisJob`、
  `InsightAnalysisJob`、`EmbeddingJob`、`MemoryCompactionJob`。
- `app/jobs/in_process.py` —— 本地调度器。把 `JournalCreated` 扇出为「向量化 + 记忆蒸馏 + 洞察分析 + 目标进度」。请求期间入队的任务会在其事务**提交之后**才执行。
- `app/jobs/worker.py` —— arq worker 定义与 cron 排程（每周洞察：周一 04:00；记忆压缩：周日 05:00）。
- `app/jobs/worker_main.py` —— 容器入口（`python -m app.jobs.worker`）。

## 引擎

- **MemoryEngine**（`app/services/memory_engine.py`）+ `journal_extractor.py`：
  从日志正文中抽出第一人称陈述，按主体聚桶；只有当某个桶越过 §83 的
  证据数 / 置信度阈值后，才会晋级为一条 `Memory`。
- **InsightEngine**（`app/services/insight_engine.py`）基于规则对日志做检测：
  话题复现 → `TREND`，情绪走向 → `RISK`/`ACHIEVEMENT`，书写频率 → `BEHAVIOR_CHANGE`，
  目标停滞 → `RISK`，目标动能 → `GOAL_PROGRESS`，成果措辞 → `ACHIEVEMENT`，
  下一步建议 → `SUGGESTION`。每条规则的标题都是**稳定**的，因此重复运行只会原地刷新已有记录，
  不会堆叠近似重复行。注意 `generate()` 只返回本次**新建**的洞察 —— 要看完整列表请查 `GET /insights`。

---

## 开发

```bash
make lint        # ruff（后端）+ next lint（前端）
make test        # 后端 unittest 测试套件
make typecheck   # tsc --noEmit
make migrate     # alembic upgrade head
```

后端测试覆盖核心 API 流程、AI 层（Agent、工具、权限、RAG、SSE 事件顺序）以及任务层（记忆流水线、目标进度、各引擎）。

## 许可证

私有项目 —— 未授予任何许可。
