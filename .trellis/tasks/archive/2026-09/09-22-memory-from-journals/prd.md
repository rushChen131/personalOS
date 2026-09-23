# 记忆改为从日志正文提取 + 去除手动录入

## Goal

PersonalOS 里，**「日志」才是用户唯一的输入口**。但目前：

1. 记忆页有一个「新增记忆」表单，用户能手动往记忆库里塞条目 —— 这与「记忆是系统从日志里沉淀出来的认知」这个定位矛盾，也让记忆库被随手输入的测试数据污染。
2. 记忆的生成链路是 `Event → Candidate → Memory`，**事件（Event）成了中间概念**，用户需要额外维护它，认知负担重。

本任务把链路改成 **`Journal → Candidate → Memory`**：用户每天写日志，系统直接从**日志正文**里提炼事实/偏好/模式，达到证据阈值后晋级为记忆。同时**彻底去掉事件（Event）这个面向用户的概念**（时间线、事件接口、Copilot 的事件工具），并去掉记忆的手动录入。

## Requirements

### R1 — 去掉记忆的手动录入

- 前端 `app/memories/page.tsx` 移除「新增记忆」`Card`（内容输入 + 类型选择 + 添加按钮），及其 `content` / `type` 状态与 `useCreateMemory`。
- 后端删除 `POST /memories`（`memory.py::create_memory`）与 `MemoryService.create`。
- 后端删除 `MemoryCreate` schema。
- 前端删除 `api.createMemory` 与 `useCreateMemory`。
- 记忆页只保留**搜索 + 列表浏览**（只读）。

### R2 — 记忆改为从日志正文提取

- 新增日志抽取器：从 `Journal.content` 中按规则识别可沉淀的陈述句，产出候选记忆。
- `MemoryEngine` 的主入口从 `ingest_event(...)` 改为 `ingest_journal(...)`：
  - 以**日志正文**为证据来源，而不是事件标题。
  - 仍走 `Candidate → 阈值 → promote` 的 §83 策略（不破坏既有设计）。
  - `MemorySource.source_type` 从 `"EVENT"` 改为 `"JOURNAL"`，`source_id` 指向 journal id（可追溯性来自 §19）。
- `MemoryAnalysisJob` 从「按 event_id 查事件」改为「按 journal_id 查日志」。
- `InProcessDispatcher._on_journal_created` 增加 `memory_analysis` 分派（原先只派 insight）。

### R3 — 去掉「事件」这个面向用户的概念

- **前端**：删除 `/timeline` 路由与侧边栏入口（时间线就是事件列表）。删除 `api.listEvents/createEvent/getEvent/timeline/stats`、`useEvents/useCreateEvent/useTimeline/useStats`、`Event/EventCreate/TimelineItem/StatsResponse` 等仅事件使用的类型与 i18n 文案。
- **后端**：删除 `api/v1/event.py` 路由注册、`EventService`、`EventRepository`、`EventCreate/EventResponse/TimelineItem/Stats*` schemas。
- **AI 层**：删除 `query_events` / `create_event` 工具与 `_run_query_events` / `_run_create_event`；各 agent 的 tools 列表相应调整；`mock_gateway` 的事件意图分支与 `extract_event` 标题解析逻辑删除。
- **上下文投影**：`context.py` 的 `recent_events` / `underlying_events` 块改为基于**日志**（`recent_journals`）。

### R4 — 数据层保留（**不删表、不删列、不改 DDL**）

沿用上一轮的既定原则：**能删的是代码入口与 UI，不能删的是模型/表/历史契约**。

- `Event` / `EventGoal` / `Tag` / `EventTag` 模型与表**保留**。
- `Journal.events` 关系保留（否则 mapper 解析失败）。
- 洞察引擎**本轮不改**（它仍读 events 表；表在、数据在，逻辑照常跑）。

> 报告引擎已在 R6 中整体移除，属本任务范围。

### R5 — 移除独立聊天页，改为右侧面板的历史记录

- 删除 `/chat` 路由与侧边栏入口。聊天能力完全收敛到右侧 Copilot 面板。
- Copilot 面板头部新增**「历史」按钮**，点击展开/收起历史对话列表。
- 历史列表数据来自已有的 `GET /chat/conversations`；点选某条会话时用 `GET /chat/conversations/{id}` 拉取消息并**回填到面板消息流**，可继续接着聊（沿用该 `conversation_id`）。
- 新增「新对话」动作：清空消息流与 `conversation_id`。
- 页面切换时（`context.type/id` 变化）仍重置当前会话，与既有行为一致。

### R6 — 删除报告（Report）模块

- 前端删除 `/reports` 与 `/reports/[id]` 路由、侧边栏入口、`useReports/useReport/useGenerateReport`、`api` 中的报告方法、`Report/ReportSection` 类型、全部 `reports.*` / `nav.reports` i18n 文案。
- 后端删除 `api/v1/report.py` 路由注册、`ReportService`、`ReportEngine`、`ReportRepository`、`Report*` schemas、`REPORT_NOT_FOUND`、AI 工具 `query_reports` 及各 agent tools 列表中的它。
- 上下文投影移除 `report` / `historical_reports` / `underlying_events` 块。
- `DailyReportJob` 与 worker 的 report cron 移除；`REGISTRY` 去掉 `"report"` / `"daily_report"`。
- **数据层保留**：`reports` / `report_definitions` 表与 `Report` / `ReportDefinition` 模型保留（避免 mapper 解析失败），`alembic check` 仍需 clean。

### R7 — 日历工具

Copilot 已注册 `calendar_sync`（返回 `not_configured`）。本轮**不动**，仅确认工具注册表在移除报告后仍自洽。

## Acceptance Criteria

- [ ] 记忆页无任何表单/输入框（除搜索框外），无「新增记忆」入口。
- [ ] `POST /api/v1/memories` 返回 405 或 404。
- [ ] 前端 `grep -ri "createMemory\|useCreateMemory\|MemoryCreate" src/` 无残留。
- [ ] 后端 `grep -rn "MemoryService.create\|MemoryCreate" app/` 无残留。
- [ ] `MemoryEngine.ingest_journal()` 存在；`ingest_event()` 已移除。
- [ ] 写完一条日志后，`memory_candidates` 有对应行，且 `signature` 源自日志内容。
- [ ] 日志达到阈值重复后，能 promote 出 `Memory`，其 `MemorySource.source_type == "JOURNAL"`。
- [ ] `/timeline` 路由返回 404；侧边栏无「时间线」入口。
- [ ] `/api/v1/events` 返回 404。
- [ ] AI 工具层无 `query_events` / `create_event`。
- [ ] 记忆页「搜索」功能正常（`POST /memories/search` 可用）。
- [ ] `/chat` 路由返回 404；侧边栏无「对话」入口。
- [ ] Copilot 面板有「历史」按钮，可展开历史对话列表并点选回填消息。
- [ ] Copilot 面板有「新对话」动作，可清空当前会话。
- [ ] `/reports` 与 `/reports/[id]` 返回 404；侧边栏无「报告」入口。
- [ ] `/api/v1/reports` 返回 404。
- [ ] AI 工具层无 `query_reports`。
- [ ] `ruff check` clean。
- [ ] `unittest` 全绿（含为本次改动调整后的用例）。
- [ ] `tsc --noEmit` 0 error；`next lint` clean。
- [ ] `alembic check` clean（**无 DDL 变更**）。
- [ ] smoke 测试通过（事件断言改为 404）。
- [ ] 后端 health 200；前端保留路由 200。

## Notes

### N1 — 抽取策略（记忆从日志来）

日志是**自然语言长文**，没有结构化标题，因此不能照搬按「标题首实体」分桶的做法。采用**句式触发 + 实体分桶**：

- 识别「认知型陈述」的标记：`我是/我喜欢/我偏好/我习惯/我倾向/我决定/我意识到/我擅长/我不喜欢/我讨厌/我的…是`，英文 `I am/I like/I prefer/I usually/I tend to/I decided/I realized/I'm good at`。
- 每条命中的句子产出一个候选，`topic` 取该句的**首个实体词**（复用 `_topic_key`），`content` 保留整句原文（比拼接的模板句更有信息量）。
- 同一 topic 在窗口期内反复出现（不同句子）才累积证据、才可能晋级 —— 保持 §83 的「不因单次提及就成为记忆」。
- 置信度公式沿用现有的 `_confidence(evidence_count, distinct_titles)`。

### N2 — 为什么保留 Event 表和模型

`Journal.events`、`User.events`、`Goal.events`、`Tag.events`、`Project.events` 等 relationship 都用字符串引用了 `Event`；删掉 `Event` 类会让 SQLAlchemy mapper 在配置期直接抛 `InvalidRequestError`（与上一轮 `Project` 同理）。且 `insight_engine` / `report_engine` 仍查询 events 表。

### N3 — i18n

移除文案时 **zh 与 en 两个字典必须同时删**，否则三层回退会让残留的 en 条目以英文形式漏出。

### N4 — 验证纪律

- 不要动 `frontend/.next` 与 dev server；前端验证用 `tsc --noEmit` + `next lint`，**不要**在 dev 运行时跑 `npm run build`。
- 删路由后若 `tsc` 报 stale 类型，**只删对应的 `.next/types/app/<route>` 子目录**，不要 `rm -rf .next`。
- 保持「只实现，不 git commit」。
