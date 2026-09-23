# PersonalOS V1.2 技术设计（父任务）

## 架构总览

```
Frontend (Next.js) ──REST/SSE──► FastAPI ──► Application Service ──► Repository ──► SQLAlchemy ──► SQLite(PG-target)
                                      │                                    ▲
             AgentRuntime ◄───────────┤                                    │
               ├── AgentRegistry(7)                                        │
               ├── ContextRuntime ──────┼──────────────────────────────────┤
               ├── ToolRegistry ────────┼──────────────────────────────────┤
               ├── RAGRuntime ──────────┘
               └── ModelGateway ──► OpenAIClient | MockLLM (router 选择)
```

### 分层边界（`技术设计.md` §87）
- FastAPI：认证/数据/权限/业务/事务
- Agent Runtime：理解/推理/Tool Calling/RAG/AI 生成
- 禁止 Controller 直接调 LLM / 直接写库

## 关键设计决策

### D1. 数据库双模式
- **抽象**：SQLAlchemy 2 async，ORM 层与方言无关
- **向量列**：SQLAlchemy `Vector(1536)` 类型在 PG 生效；SQLite 模式中列声明为 JSON（用 `JSON`），通过类型注释或条件映射实现
- **检索**：定义 `EmbeddingProvider` 接口。PG+pgaisum/pgvector → `vector_cosine_ops`；SQLite → 关键词（ILIKE/`instr`）+ 元数据过滤 + 时间过滤的组合，产出同样结构的检索结果
- **DDL**：Alembic migration 同时生成。SQLite 用 `sqlite:///./personalos.db`；PG 用 `postgresql+asyncpg://...`
- 驱动选择：`asyncpg` 仅 PG 使用；SQLite 用内置 `aiosqlite`

### D2. AI Mock 策略
- `ModelGateway` 由配置 `LLM_PROVIDER`（openai/mock）选择实现
- MockLLM：检测 prompt 中的特定指令标记（如 `extract_events`），返回规则式 JSON；否则返回提示引导的回答文本
- 让各 Agent 的 system prompt 明确要求结构化 JSON 输出，Mock 与真实模型走同一解析路径（json.loads + Schema 校验）

### D3. Agent 执行流（无 Key 也走通）
```
chat POST → AgentRuntime.run → ContextRuntime.build → 注入 AgentContext
        → BaseAgent.execute → (模型可能返回 tool_calls) → ToolRegistry.execute(tool, args, ctx)
        → 结果回填 → 最终 AgentResult → 存 agent_runs/tool_runs → SSE 输出
```
- Mock 模式默认直接调工具组合（如 journal 页 → query_events + search_memory），拼装回答
- 真实模式：OpenAI chat.completions with tool calling 循环（≤3 轮）

### D4. SSE 协议（`技术设计.md` §41）
```
event: start    data: {"run_id": "..."}
event: thinking data: {"message": "..."}
event: tool_call   data: {"tool": "...", "arguments": {...}}
event: tool_result data: {"tool": "...", "count": 2}
event: content  data: {"delta": "..."}
event: done     data: {}
```

### D5. 统一响应
- 成功：`{success: true, data, request_id}`
- 失败：`{success: false, error:{code,message}, request_id}`
- 用 FastAPI middleware 注入 request_id；错误交给全局 exception handler 转换

### D6. 认证（V0.1 简化）
- `POST /auth/login` 用固定 dev 用户（seed），返回 JWT
- header `Authorization: Bearer` → user dep
- 不引入注册流程（dev seed 用户 usr_001）

### D7. Event → 派生（Embedding/Goal progress/Memory/Insight）
- SQLite 本地：`POST /journals` 后同步或异步触发 JournalAgent 抽事件（先同步可验证，标注可选 async）
- 事件总线：内存版 EventBus（无 Redis 时），提供 `publish/subscribe`；arq worker 仅在 PG+Redis 模式启用

### D8. 前端结构
- App Router；`src/features/*` 按域组织；`src/stores/` Zustand（auth/ui/memory）；`src/services/` API client（fetch + SSE reader）
- AI Copilot：全局 layout 右侧抽屉，读取当前 `pathname` → 调 `/context` → 展示上下文

## 数据流主链路（验收路径）
```
Journal POST → 保存 journal（原文）→ JournalAgent.extract_events
  → 用户确认 → events POST → EventCreated 事件
    → memory 候选（达标生成 Memory，含来源）
    → goals 进度刷新（按 event_goals）
    → insights 分析（有 key 时）
  → Timeline/Stats 展示
  → Chat: "我最近在研究什么？" → RAG 检索 → 回答
  → Report generate → 报告 JSON
```

## 兼容性 / 回滚
- 方言差异集中封装在 `app/infrastructure/database` 与 `app/infrastructure/llm`；业务层不感知
- SQLite 与 PG 的 embedding 差异只影响 RAG 质量，不影响数据链路
- 回滚点：每个 child 完成任务前 `task.py archive` 不触发；代码回滚靠 git

## 端口约定
- backend: 8000（/docs），frontend: 3000，postgres: 5432，redis: 6379，minio: 9000/9001