# PersonalOS V1.2 执行计划（父任务）

## 执行顺序

依赖链：**backend-core → backend-ai → backend-jobs**；frontend 与 infra-docs 在 backend-core 建立 API 契约后并行。

```
Phase A  backend-core   （第 1 顺序任务，先启动）
Phase B  backend-ai     （依赖 core 的 repository 完成）
Phase C  backend-jobs   （依赖 ai 的 agent/tool）
Phase D  frontend       （依赖 core 的 API 契约）
Phase E  infra-docs     （依赖 backend/frontend Dockerfile）
Phase F  父任务集成验收  （跑通最小闭环 + 全站点导航）
```

## 验收门

| Phase | Gate |
|-------|------|
| A | `uvicorn app.main:app` 起，/health ok，全部路由注册，SQLite 建表，seed 用户 |
| B | MockLLM 下 chat SSE 全事件序列；journal 抽事件；memory 检索 |
| C | report generate 产出结构化报告；insight 生成；EventBus 触发链 |
| D | Dashboard/Journal/Timeline/Goals/Reports 页面 + Copilot 侧栏可导航 |
| E | docker-compose.config 通过（无 docker 则静态校验） |
| F | 手工走通：输入一句话 → 事件 → 时间线 → 目标 % → Chat 问答 → 报告 |

## 子任务清单（各 child 自行维护 implement.md）

1. **backend-core** — models(全部表) / alembic / repositories / services / schemas / api.v1 全部路由 / auth / seed / context API / events stats+timeline / memories search（关键词版）
2. **backend-ai** — Gateway(openai+mock) / ModelRouter / Runtime / ContextRuntime / BaseAgent / 7 agents / tools / RAG / ActionProposal / agent_runs+tool_runs 记录
3. **backend-jobs** — EventBus / ReportEngine / InsightEngine / worker 骨架 / journal→event 触发链
4. **frontend** — Next.js 脚手架 / api client / stores / layout+sidebar+copilot / 各页面 / SSE 组件 / echart 组件
5. **infra-docs** — docker-compose / backend Dockerfile / frontend Dockerfile / .env.example / README / Makefile

## 环境约束执行方式

- 无 docker/pg/redis：本地验证一律 SQLite + 内存 EventBus + MockLLM；docker-compose 文件做静态交付
- 无 OpenAI key：MockLLM 兜底；key 配置在 `.env`（`OPENAI_API_KEY`）后走真实调用
- 前端无 `docker compose` 时用 `npm run dev` 本地联调

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| V1.2 范围过大，一次会话难以全量 | 按 Phase 顺序推进，每 phase 独立验收后可停下 |
| SQLite 与 PG 方言差异 | D1 集中抽象；embedding 列在 SQLite 用 JSON，PG 用 Vector |
| 无 key 时 AI 链路无法体现智能 | Mock 生成结构化结果，保证链路可走、可测 |
| 前端依赖重（shadcn） | 用等价 Tailwind 组件 + 轻依赖实现，避免需写 shadcn CLI |

## 完成标准（父任务）

- 最小闭环可本地跑通（Journal→Event→Timeline→Goal→Chat→Report）
- 全部 API 注册且有 SQLite 可执行测试
- 前端可 `npm run dev` 访问到 Dashboard
- 文档 & compose 文件就绪
- 前后端 lint/typecheck 通过
- 每条 AI 执行有 agent_runs 记录