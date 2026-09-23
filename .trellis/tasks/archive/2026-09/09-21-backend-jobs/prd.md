# backend-jobs：报告引擎 / Insight / 事件总线

## Goal
实现后台任务层：EventBus（内存 + Redis 适配）、Journal→Event 触发链、ReportEngine、InsightEngine、Goal 进度更新、worker 骨架。SQLite 本地用内存总线 + 同步/轻量触发，PG+Redis 环境可切 arq。

## Requirements

### Event Bus（`技术设计.md` §80-81）
- `EventBus.publish(event_type, payload)` / `subscribe(event_type, handler)`
- 事件：JournalCreated, EventCreated, GoalCreated, GoalUpdated, MemoryCreated, InsightCreated, ReportGenerated
- 内存实现（无 Redis）；`RedisEventBus` 预留（PG 生产模式）
- EventCreated 触发：EmbeddingJob、GoalProgressJob、MemoryAnalysisJob、InsightAnalysisJob

### ReportEngine（§85-86）
- `ReportEngine.generate(user_id, definition_id, start_date, end_date)`
- 流程：Load Definition → Load Events → Goals → Projects → Memories → Insights → Aggregate → (Agent/LLM or 规则) → Report JSON
- Report JSON 统一结构：summary{text,metrics}, activity{total_hours,distribution}, goals[], projects[], insights[], risks[], recommendations[], next_actions[]
- ReportAgent 可用时用 AI 生成文字部分；无 key 走统计规则生成基础 JSON

### InsightEngine（§84）
- 周期（日/周）聚合：最近 Event + 历史 + Goal + Memory → Aggregation → Pattern Detection（规则：时间投入、目标停滞、行为变化）→ (LLM or 规则) → InsightCandidate → Confidence Filter → Insight 落库

### Goal 进度
- GoalProgressJob：按 event_goals 关联事件统计 → 更新 goal.progress

### Embedding
- EmbeddingJob：为 journal/event/memory content 生成 embedding（有 key 时调 embedding 模型；无 key 时跳过并记录）。SQLite 中 embedding 列 JSON 存向量或空

### Worker 骨架
- `app/jobs/worker.py`：arq Worker 定义（生产）+ `app/jobs/in_process.py`：本地同步触发实现（dev 默认）
- 定时：daily summary / weekly report（schedule 注释标注，不在本地自动跑）

## Acceptance Criteria
- [ ] 建 journal → EventCreated 链自动触发 goal progress 更新 + memory 候选
- [ ] `POST /api/v1/reports/generate` 无 key 生成结构化报告 JSON（summary/activity/goals/insights/next_actions）
- [ ] reports 内容含 activity 时间分布（按 type 聚合）
- [ ] insight 规则引擎对"目标连续 2 周无事件"产出 RISK 类型 insight
- [ ] worker.py 定义完整（arq）；in_process 模式可手动 run 报告任务
- [ ] ruff 通过

## Notes
- 依赖 backend-core(model/repo) + backend-ai(agent/tool/llm)
- 本任务让 report/insight 从 backend-core 的基础统计版升级到 Engine 版
- 无 key 时规则引擎兜底，有 key 时调用 ReportAgent/InsightAgent