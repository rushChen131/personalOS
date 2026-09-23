# 实现记录 — 记忆改为从日志正文提取 + 去除事件/报告/独立聊天页 + 洞察转向日志

## 一句话总结

把 PersonalOS 的主链路从 `Journal → Event → Memory` 收敛为 **`Journal → Memory`**：日志成为**唯一的人工输入口**，记忆与洞察都由日志正文自动抽取；同时移除 Event、Report 两个面向用户的概念面，以及独立的 `/chat` 页面（收敛为右侧 Copilot 面板内的历史视图）。

**全程零 DDL 变更**：`alembic check` 保持 clean，`Event`/`Report`/`ReportDefinition`/`Tag`/`EventGoal`/`EventTag` 模型与表一律保留。

---

## 1. 后端

### 1.1 记忆从日志正文提取（R2，核心）

| 文件 | 改动 |
| --- | --- |
| `app/services/journal_extractor.py` | **新增**。规则式抽取器：`_ZH_MARKERS` / `_EN_MARKERS` 句式触发词，`_NOISE_PATTERNS` 去噪，`_SENTENCE_SPLIT` 按中英标点切句，`extract_statements(content, *, max_statements=10)` |
| `app/services/memory_engine.py` | `ingest_event()` → **`ingest_journal()`**；`_topic_key` 重写（见下）；`MemorySource.source_type` 由 `"EVENT"` 改为 `"JOURNAL"` |
| `app/jobs/handlers.py` | `MemoryAnalysisJob` 改为按 `journal_id` 查 `Journal` 后调 `ingest_journal`；`EmbeddingJob` 改为嵌入日志；`GoalProgressJob` 改为按日志中是否提到目标标题计量投入；`DailyReportJob` **删除** |
| `app/jobs/in_process.py` | `REGISTRY` 去掉两个 report 条目；只订阅 `JournalCreated`；日志创建后 fan-out 到 `embedding / memory_analysis / insight_analysis / goal_progress` |

#### `_topic_key` 重写（本轮最大技术难点）

原实现直接取「首个非停用词」，在中文长文上产出**整句碎片**（`我喜欢用`、`我习惯早上写`），导致同一主题永远聚不到一个桶里 —— 而 §83 的晋级**必须**依赖聚桶，聚不到就永远不晋级。

新实现分三步：

1. **`_normalize`** —— 小写、展开 `I'm → i am`、剥离非 `\w`/非 CJK 字符。
2. **`_strip_lead`** —— 循环剥离「认知开场词 → 助词 → 时间限定词 → 助词」，直到稳定：
   - `_CJK_OPENERS`：`我喜欢`/`我通常`/`我倾向`/`我意识到`/`我不擅长` …（含短前缀 `不喜欢`/`擅长`/`决定` …）
   - `_CJK_PARTICLES`：`用在从对给和跟把`
   - `_CJK_TIME_QUALIFIERS`：`周末`/`工作日`/`早上`/`每天` …
3. **`_latin_entity`** —— 若片段里嵌了拉丁词（如未分词的中英混排 `rust写后端`），用 `_LATIN_RUN` 把 `rust` 抠出来当桶键；含 `.` 的（如 `node.js`）要求纯字母才承认，避免把 `etc.` 当实体。

最终退化为「剥离后取前 12 字」。

实测分桶（全部收敛到同一桶，这是晋级的前提）：

| 输入 | 桶键 |
| --- | --- |
| `我喜欢用rust写后端` / `我打算深入学Rust` / `Rust 很适合我` / `我平时写 Rust` | `rust` |
| `我通常在周末读书` | `读书` |
| `我喜欢 dark mode` | `dark` |
| `我更喜欢用TypeScript写前端` | `typescript` |

#### 晋级阈值（实测标定）

```
MIN_EVIDENCE_COUNT = 3       # 命中陈述数
MIN_DISTINCT_TITLES = 3      # 不同陈述文本数
PROMOTION_THRESHOLD = 0.75   # 置信度
CONFIDENCE_BASE = 0.5        # volume = min(1, n/20), variety = min(1, distinct/5)
```

置信度曲线（实测）：

| 命中数 | 不同陈述 | 置信度 |
| --- | --- | --- |
| 3 | 3 | **0.69** ← 不达标 |
| 4 | 4 | 0.75 ← 刚好达标 |
| 5 | 5 | 0.81 |
| 10 | 5 | 0.88 |
| 20 | 5 | 1.00 |

> ⚠️ 关键坑：`3 命中 / 3 不同` 只有 **0.69**，**卡在阈值下方不晋级**。写种子数据时若每个主题只贡献 3 条陈述，会得到「候选堆积但零记忆」的假象。种子数据已按此修正（见 3.2）。

### 1.2 去掉记忆手动录入（R1）

- `app/api/v1/memory.py`：删除 `POST /memories`（`create_memory`）。
- `app/services/memory_service.py`：删除 `create()`，类退化为只读，并加 docstring 说明「记忆由日志蒸馏而来」。
- `app/schemas/common.py`：删除 `MemoryCreate`。

### 1.3 去掉事件（R3）

- **删除文件**：`app/api/v1/event.py`、`app/services/event_service.py`、`app/repositories/event_repository.py`。
- **删除 schema**：`EventCreate`、`EventResponse`、`TimelineItem`、`StatsTimeSlice`、`StatsResponse`。
- `app/main.py`：`event` 路由取消注册。
- `app/core/errors.py`：删除 `EVENT_NOT_FOUND`。
- `app/services/goal_service.py`：删除 `get_related_events()`。
- **AI 层**：`query_events` → **`query_journals`**（查询 `Journal`，支持 `ilike` 正文过滤）；删除 `create_event` / `delete_event` 工具与 `WRITE_EVENT` / `DELETE_EVENT` 权限常量。
- **6 个 Agent 的 tools 列表**全部重排（`ReportAgent` 删除，7 → 6）：

| Agent | tools |
| --- | --- |
| `PersonalManagerAgent` | `query_journals`, `query_goals`, `search_memory`, `query_insights` |
| `JournalAgent` | `query_journals`, `search_memory`（只读，权限 `{READ}`） |
| `GoalAgent` | `query_goals`, `query_journals` |
| `MemoryAgent` | `search_memory`, `query_journals` |
| `InsightAgent` | `query_insights`, `query_journals`, `query_goals`, `search_memory`, `create_insight` |
| `CoachAgent` | `query_journals`, `query_goals`, `search_memory` |

- `app/ai/gateway/mock_gateway.py`：`synthesize()` 的 `events` 分支改 `journals`；`plan()` 删除事件/报告意图；`compose()` 文案改为 journals/goals/memories/insights；**删除约 6.6k 字符**死代码（`_EVENT_VERBS`、`extract_event`、`_TIME_OF_DAY_MINUTES`、`_duration_from_time_of_day`、`_derive_title`、`_derive_type`、`event_extraction` kind）。
- `app/ai/gateway/model_router.py`：`_HEAVY_TASKS` 去掉 `"report"`。
- `app/ai/context.py`：`PAGE_CONTEXT` 只保留 `dashboard/goal/goals/journal/journals/memory/memories/insight/insights`；删除 `_report_block` / `_underlying_events` / `_historical_reports` / `_recent_events`。
- `app/services/context_service.py`：改为日志中心，`related_events` / `related_reports` → **`related_journals`** + `related_memories`。

### 1.4 去掉报告（R6）

- **删除文件**：`app/api/v1/report.py`、`app/services/report_service.py`、`app/services/report_engine.py`、`DailyReportJob`。
- `app/repositories/insight_report_repository.py`：删除 `ReportRepository`（保留 `InsightRepository` / `ConversationRepository`）。
- `app/core/errors.py`：删除 `REPORT_NOT_FOUND`。
- AI 层删除 `query_reports` 工具与 `WRITE_REPORT` 权限常量。
- `app/schemas/common.py`：删除 `ReportGenerateRequest`、`ReportResponse`。

### 1.5 数据层保留（R4）

保留 `Event` / `EventGoal` / `Tag` / `EventTag` / `Report` / `ReportDefinition` 模型与表，以及 `Journal.events` 等字符串 relationship。

> 原因：这些 relationship 用**字符串**引用 `Event`，删类会让 SQLAlchemy 在 mapper 配置期直接抛 `InvalidRequestError`。同理保留 `Report` 以免 `ReportDefinition` 的引用断裂。

### 1.6 收尾清理（两处遗漏，验证阶段发现）

| 文件 | 问题 | 处置 |
| --- | --- | --- |
| `app/jobs/worker.py` | arq worker 里仍定义 5 个 report cron（`daily/weekly/monthly/quarterly/yearly_report`），且 `WorkerSettings.build()` 的 `cron_jobs` 仍按 `"report"` / `"daily_report"` 调用 —— 这两个 job type 已从 `REGISTRY` 删除，**生产 worker 会在启动后每次 cron 触发时返回 `unknown job_type`** | 删除全部 report 任务与 cron；`functions` 保留 `run_job` / `weekly_insights` / `memory_compaction`；`cron_jobs` 只留每周洞察（Mon 04:00）与记忆压缩（Sun 05:00） |
| `app/ai/rag/runtime.py` | `_keyword_events()` 仍查 `Event` 表并返回 `kind="event"`，而 `search()` 把 memories + events 合并返回。事件已无写入路径 → 该分支永远返回空 | 改写为 `_keyword_journals()`：查 `Journal`，按 `occurred_at` 排序，返回 `kind="journal"`；`filters["since"]` 改比 `occurred_at`；移除 `Event` import |

### 1.7 洞察引擎改为读日志（本轮补充，原列为「已知取舍」的遗留项）

`app/services/insight_engine.py` **整文件重写**，彻底移除 `Event` 依赖。

#### 为什么要重写而不是改查询

旧规则的判定条件**建立在事件独有字段上**，日志根本没有这些字段：

| 旧规则 | 依赖字段 | 日志是否有 |
| --- | --- | --- |
| `_detect_investment_shift` | `event.type`（活动类型）+ `event.duration_minutes` | ❌ 两者都无 |
| `_detect_anomalies` | `event.duration_minutes` 的当日总量 | ❌ |

所以不是「换个表查」，而是**必须换一套信号**。

#### 事件信号 → 日志信号 映射

| 旧规则（事件） | 新规则（日志） | 类型 | 判据 |
| --- | --- | --- | --- |
| `_detect_investment_shift`（时间投入迁移） | `_detect_recurring_topics`（话题复现） | `TREND` | 同一主题跨 ≥3 篇、占比 ≥25% |
| `_detect_anomalies`（异常高强度日） | `_detect_mood_trend`（情绪走向） | `RISK` / `ACHIEVEMENT` | `mood` 字段 ≥4 篇中负面 ≥3 且占比 ≥50%／某正面情绪 ≥3 次 |
| —（新增） | `_detect_journal_volume_change`（书写频率） | `BEHAVIOR_CHANGE` | 周环比变化 ≥40%（基准周 ≥3 篇） |
| —（新增） | `_detect_achievements`（成果措辞） | `ACHIEVEMENT` | 命中 `_ACCOMPLISHMENT_MARKERS` 的条目 ≥2  |
| 旧 `_detect_stagnant_goals`（保留） | 同左，改为按日志正文匹配 | `RISK` | ACTIVE 目标在窗口内零提及 |
| 旧 `_detect_goal_progress`（保留） | `_detect_goal_momentum` | `GOAL_PROGRESS` | 进度 ≥90%，或进度 ≤20% 但窗口内被提及 ≥3 次 |
| 旧 `_detect_suggestions`（保留） | 同左 | `SUGGESTION` | 有 ACTIVE 目标但一周无日志；或记录里完全没有学习/健康类主题 |

**结论**：`type` / `duration_minutes` 两个字段的语义空缺，分别由**「自由文本主题」**和**「可选 `mood` 字段」**补上 —— 这两个是日志真正携带的结构化/半结构化信号。

#### 复用记忆引擎的词表（`_topics` 与 `_topic_key` 的分工）

新规则需要把日志正文变成「主题」。这里**复用**了 `memory_engine` 的 `_normalize` / `_LATIN_RUN` / `_EN_STOPWORDS` / `_CJK_STOPWORDS`，理由是：**「什么算同一个主题」这件事，两层必须一致**，否则记忆认得的主题洞察认不得。

但 `_topic_key` **不能直接用于话题复现统计** —— 这是本轮踩到最深的坑：

- `_topic_key` 的设计目标是**把陈述分桶进记忆**，为此它刻意只返回**首个实体**，保证桶键稳定、证据能累积。这是对的。
- 话题复现要回答的是另一个问题：「作者反复在写什么？」只取首个实体就丢掉了大部分答案。
- 实测：`"I am learning Rust ownership."` 被 `_topic_key` 归到 **`learning`** 而不是 `rust`。三篇 Rust 日志因此碎成 `rust`(2) / `learning`(1) / `went`(1)，**永远到不了 `MIN_ENTRIES_FOR_TOPIC = 3`**。

处置：新增 `_topic_terms(text) -> set[str]`，**保留全部**实体而不是挑一个：

1. 所有 `_LATIN_RUN` 命中（`rust`、`agentscope`、`typescript` …），长度 ≥3 且不在 `_EN_STOPWORDS` / `_TOPIC_NOISE` 中；
2. 追加 `_topic_key` 的结论（覆盖纯中文句的主语，如 `我喜欢用 rust 写后端` → `rust`）。

`_TOPIC_NOISE` 是一张**刻意收窄**的动词/副词表（`spent` / `went` / `today` / `working` …）。因为话题复现统计的是**原始提及次数**，不加过滤时「昨晚花了很久」这类叙事句会让 `spent` 看起来像反复出现的主题。表保持很小 —— 放宽会开始吃掉真实体。

#### 单日聚集不能当作噪声（第二个坑）

修完 `_topics` 后规则**仍然不触发**。直接探针（绕开 dispatcher 时序、直连库）打出了决定性输出：

```
'Rust ownership'       topics=['learning', 'ownership', 'rust']
'Rust traits'          topics=['rust', 'this']
'Rust borrow checker'  topics=['faster', 'getting', 'rust']
in_window: 5
=== _detect_recurring_topics ===
（空）
```

`rust` 已经在 3 篇里都出现了，但旧判据要求 `len(distinct_days) >= 2`，而这 3 篇的 `created_at` 全是同一天 —— **日志本来就常常是在一个晚上连着写的**。这个「跨天」条件是从事件时代（事件天然按时间分散）带过来的，对日志是错的。

处置：把跨天从**硬门槛**降为**加权条件** —— 单日聚集需要更高的占比才能成立：

```python
if share < 0.25:                          # 任何时候都要够突出
    continue
if len(distinct_days) < 2 and share < 0.5:  # 只在同一天写的，要 ≥50% 才认
    continue
```

修正后：

```
[TREND] conf=0.78 Recurring focus: rust
    'rust' comes up in 3 of your last 5 entries (60%) in one sitting,
    including: Rust borrow checker, Rust ownership, Rust traits.
```

文案也跟着分支：跨天说 `across N days`，单日说 `in one sitting`。

#### 重复写入竞态（第三个坑）

`InProcessDispatcher` 在**每篇日志写入时**都触发一次 `insight_analysis`，所以连续写 5 篇日志 = 引擎跑 5 次且**互相重叠**。两个并发 pass 可能都在对方提交前读到「没有这条洞察」，于是插入两行**标题完全相同**的记录。实测到的证据（同一秒、标题逐字节相同）：

```
DUP x5  Goal stalled: Read 12 books this year   at 01:59:51 / 01:59:52
```

两个根因，分别处置：

1. **标题不稳定** —— `_detect_achievements` 原来把实时计数写进标题（`"4 notable outcomes this week"` → `"2 notable outcomes"` → `"1 notable outcome"`），标题一变，基于标题的去重全部失效。
   → 标题改为**常量** `"Notable outcomes on the record"`，计数只放在 `content` 里。
2. **并发竞态** —— `InsightAnalysisJob` **每次运行都新建一个引擎实例**，所以实例级 `asyncio.Lock` 无效。
   → 加**模块级 per-user 锁注册表**（`_LOCKS` / `_lock_for(user_id)`），按用户串行化「先查后插」，无需任何 schema 变更。

#### 内容刷新（第四个坑）

标题稳定之后，新问题冒出来了：引擎早期跑出的那行写的是 *"none of your last **2** journal entries"*，之后每次运行都因去重**直接跳过**，于是这句错误的计数被永久冻结在库里。

处置：把「跳过式去重」`_is_duplicate` 换成 **`_find_existing` + `_refresh`** —— 命同标题时**原地更新** `content` / `insight_type` / `confidence` / `importance` / `evidence`。

> ⚠️ 由此 `generate()` 的返回值语义需要明确：它只返回**本次新建**的洞察，命中已有标题的记录是「刷新」而非「新建」，**不会出现在返回值里**。需要完整列表请查 `/insights` 接口；`self.last_run = {created, refreshed, evaluated}` 提供拆分计数。测试断言请对**落库结果**做，不要对 `generate()` 的返回值做 —— 这个坑已经把 `test_insight_engine_flags_stagnant_goal` 打红过一次。

#### 定稿常量

```python
STAGNATION_DAYS = 14
MIN_CONFIDENCE = 0.5
MIN_ENTRIES_FOR_TOPIC = 3
MIN_ENTRIES_FOR_MOOD = 4
MIN_ENTRIES_FOR_ACCOMPLISHMENT = 2
NEGATIVE_MOODS / POSITIVE_MOODS   # 情绪词表
```

---

## 2. 前端

### 2.1 记忆页只读化（R1）

- `app/memories/page.tsx`：删除「新增记忆」Card、`MEMORY_TYPES`、`useCreateMemory`；页头新增 `memories.derivedHint` 提示「记忆由日志自动提炼」。
- `hooks/useApi.ts`：删除 `useCreateMemory`。

### 2.2 删除多余路由（R3 / R5 / R6）

| 删除内容 | 说明 |
| --- | --- |
| `app/timeline/` + `nav.timeline` | 时间线即事件列表 |
| `app/reports/` + `app/reports/[id]/` + `nav.reports` | 报告模块整体移除 |
| `app/chat/` + `nav.chat` | 收敛进右侧 Copilot 面板 |

- `components/AppShell.tsx`：`NAV` 收敛为 `/dashboard`、`/journals`、`/goals`、`/memories`、`/insights`、`/settings`。
- `lib/api.ts`：删除 `listEvents/createEvent/getEvent/timeline/stats`、`listReports/getReport/generateReport`、`createMemory`，以及悬空的 `export type { ReportSection }`。
- `types/api.ts`：删除 `EventType`、`EventCreate`、`Event`、`ReportGenerateRequest`、`ReportSection`、`Report`、`TimelineItem`、`StatsTimeSlice`、`StatsResponse`、`MemoryCreate`；`ContextResponse` 改为 `related_journals` / `related_memories`。
- `hooks/useApi.ts`：删除 `useEvents/useCreateEvent/useTimeline/useStats/useReports/useReport/useGenerateReport` 及对应 `queryKeys`。

### 2.3 Copilot 面板内嵌历史（R5）

`components/CopilotPanel.tsx` 重写，新增 `type View = "chat" | "history"`：

- 头部：**新对话**、**历史** 两个按钮；历史视图下显示 **返回**。
- `openHistory()` → `api.listConversations()`。
- `loadConversation(id)` → `api.getConversation(id)`，把 messages 映射回 `turns`，**沿用同一 `conversation_id` 可继续接着聊**。
- `startNewConversation()` → 清空 `conversationId` / `turns`。
- `useContextTarget()` 去掉 `/reports`、`/timeline` 分支。
- 消息气泡加 `whitespace-pre-wrap`（保留换行）。

> 复用既有 `GET /chat/conversations` 与 `GET /chat/conversations/{id}`，**后端无需新增接口**。

### 2.4 仪表盘改为日志中心

`app/dashboard/page.tsx` 重写：四张 StatTile 变为 **日志数 / 记忆数 / 进行中目标 / 洞察数**；两张卡片变为 **最近日志** + **目标进度**；另两张变为 **最近记忆** + **AI 洞察**。删除 `BarChart` 与事件类型分布（事件类型字段已无来源）。

### 2.5 i18n（N3）

`lib/i18n.ts`：

- **删除**：`nav.timeline`、`nav.reports`、`nav.chat`、全部 `timeline.*`、全部 `reports.*`、全部 `chat.*`、`copilot.ctx.goal` / `.report` / `.reports` / `.timeline`、旧 `dashboard.statEvents` / `.statTracked` / `.distribution` / `.distributionHint` / `.recentEvents`、`memories.addMemory` / `.placeholderContent`。
- **新增**：`copilot.newChat` / `.history` / `.back` / `.untitled` / `.historyEmpty` / `.historyError` / `.send`；`dashboard.statJournals` / `.statMemories` / `.recentJournals` / `.recentJournalsHint` / `.recentMemories` / `.recentMemoriesHint`。
- zh 与 en **两个字典同步增删**，并做了「所有 `t("…")` 键是否都在字典里」的脚本化比对（结果：无缺失）。

---

## 3. 脚本

### 3.1 `backend/scripts/smoke_test.py`

- 事件/时间线段落由「正向 CRUD 断言」改为 **404 回归断言**（`/events`、`/events/timeline`、`/events/stats`）。
- 报告段落改为 **404 回归断言**（`/reports`、`/reports/generate`）。
- `POST /memories` 断言 405/404（手动录入已移除）。
- 日志段落额外补写 3 条 Rust 相关条目，覆盖抽取链路。
- 结果：**PASSED 32 / FAILED 0**。

### 3.2 `backend/scripts/seed_demo_data.py`

- 整体改写为**日志驱动**：删除 projects / events / reports 三个段落，改为写 **20 篇日志**（首人称短段落，便于抽取器命中）。
- AgentScope 主题刻意跨 6 篇日志重复，**且每篇至少含一条首人称 AgentScope 陈述** —— 这是踩坑后的修正：只提到主题但不构成陈述，命中数会停在 3（置信度 0.69，不达标）。
- `reset_demo_data` 的遍历路径由 `(/events, /journals, /goals, /projects, /memories)` 改为 `(/journals, /goals, /memories, /insights)`。
- `[verify]` 段落同步改为 `goals / journals / memories / insights`。
- 顺带修了一个环境问题：脚本原来用 `urllib.request.urlopen`，会吃到宿主的 `HTTP_PROXY`，把 `127.0.0.1` 变成 502。改为 `build_opener(ProxyHandler({}))` 显式绕过代理（脚本只与本地 dev server 通信）。

---

## 4. 文档同步

`README.md` 里写着已删除的接口与概念，本轮一并修正：

| 位置 | 修正 |
| --- | --- |
| 首段定位 | 「journals, events, goals, projects and long-term memories」→「journals as the single authored input」 |
| API overview | 删掉 Events / Reports 两行；Memories 行的 `GET/POST` → 仅 `GET` |
| API overview | 新增引用块：说明日志是唯一人工输入，Event/Report 已从 API 与 UI 退役、模型与表保留、`POST /memories` 随之删除 |
| SSE 示例 | `create_event` / `"Created event: Rust."` → `query_journals` / 日志相关文案 |
| AI layer | 「7 agents」→「6 agents」，去掉 `report_agent` |
| Tools 清单 | `query_events`/`query_projects`/`query_reports`/`create_event`/`delete_event` → `query_journals`/`query_goals`/`search_memory`/`query_insights`/`create_insight`/`calendar_tool` |
| RAG 说明 | 「memories and events」→「memories and journals」 |
| jobs 小节 | `EventCreated → …` 的旧链路描述 → `JournalCreated → embedding + memory distillation + insight analysis + goal progress`；worker cron 去掉 daily report |
| Engines 小节 | 删除 **ReportEngine** 条目，新增 **MemoryEngine + journal_extractor** 条目 |
| 测试说明 | 「report contract, event chain」→「memory pipeline, goal progress」 |

---

## 5. 验证

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端 lint | `ruff check app/ tests/ scripts/` | **All checks passed!** |
| 后端单测 | `unittest discover -s tests` | **43 tests OK** |
| 接口冒烟 | `scripts/smoke_test.py` | **32 passed / 0 failed** |
| DDL 无变更 | `alembic check` | **No new upgrade operations detected.** |
| 前端类型 | `tsc --noEmit` | **0 error** |
| 前端 lint | `next lint` | **No ESLint warnings or errors** |
| 生产构建 | `next build` | **✓ 10 routes**（`/chat`、`/timeline`、`/reports` 均已消失） |
| 端到端种子 | `seed_demo_data.py`（干净库） | **20 日志 → 1 记忆 + 7 洞察** |
| 端到端洞察（本轮新增） | 干净库 + 5 篇 Rust 日志 + 2 个 ACTIVE 目标 | **4 洞察 / 3 类型 / 0 重复**（`ACHIEVEMENT` + `TREND: rust` + `RISK`×2） |
| 残留扫描 | `grep` 全仓（后端 app/tests + 前端 src） | 无 `EventService` / `ReportEngine` / `ingest_event` / `ReportAgent` / `useReports` / `TimelineItem` 等残留 |

**接口面收敛**：`app.openapi()['paths']` 共 **19 条**，`/api/v1/events*`、`/api/v1/reports*`、`POST /api/v1/memories` 全部消失；`/api/v1/journals`、`/api/v1/memories`、`/api/v1/chat/conversations` 保留。

**端到端产物**（干净库跑种子后 `GET /memories`）：

```
type=PATTERN  conf=0.75  importance=0.58  sources=4
content: I am using AgentScope for a multi-agent orchestration prototype
         and the message bus design is the part I keep coming back to.
```

即：4 篇不同日志的独立陈述聚成同一桶、越过 0.75 阈值、晋级为长期记忆，`MemorySource.source_type == "JOURNAL"`。

**端到端洞察产物**（日志专属，无任何事件行）：

```
[ACHIEVEMENT] conf=0.7   Notable outcomes on the record
             2 of your entries this week describe outcomes worth noting: Rust ownership, Shipped notes.
[TREND]       conf=0.78  Recurring focus: rust
             'rust' comes up in 3 of your last 5 entries (60%) in one sitting, including: ...
[RISK]        conf=0.8   Goal stalled: Ship AgentScope v1.0
             'Ship AgentScope v1.0' is ACTIVE at 0% progress but none of your last 5 journal entries mention it...
[RISK]        conf=0.8   Goal stalled: Read 12 books this year
```

其中 `"last 5 journal entries"` 是**刷新后**的正确计数（首轮写入时窗口里只有 2 篇），验证了 `_refresh` 路径确实在工作。

#### 本轮新增/强化的测试（`tests/test_jobs_layer.py`）

| 测试 | 覆盖 |
| --- | --- |
| `test_insight_engine_reads_journals_not_events` | 断言模块内**已无** `Event` 符号 |
| `test_insight_engine_detects_recurring_topic` | 回归守卫：同一天写的 3 篇 Rust 也必须产出 `TREND` |
| `test_insight_engine_detects_mood_trend_both_directions` | `RISK`（负面主导）与 `ACHIEVEMENT`（正面主导）双向 |
| `test_insight_engine_does_not_stack_duplicate_titles` | 连跑 3 次引擎后标题仍唯一 |
| `test_insight_engine_flags_stagnant_goal`（改写） | 改为断言**落库结果**，并先补 3 篇日志给规则留出上下文 |

---

## 6. 已知取舍与后续

- **洞察引擎已完全转向日志**（本轮补充完成）。`insight_engine.py` 内已无 `Event` import，`_detect_investment_shift` / `_detect_anomalies` 两个事件专属规则被话题复现 / 情绪走向替代。旧的事件型洞察（历史数据）仍留在库里，但不再刷新。
- **`Event` / `Report` 模型成为纯兼容层**：代码里已无任何读写路径。将来若做 schema 大版本清理，可连同 relationship 一起收拾。
- **抽取器是规则式的**，对「认知型陈述」句式敏感。日志写成纯叙事（「今天开了个会」）不会产出候选 —— 这是 §83「不因单次提及就成为记忆」的设计取向，但意味着**用户需要写得像自我描述**才有记忆产出。
- **晋级门槛偏保守**（3 条命中/3 条不同陈述只有 0.69，实际需要 4 条以上）。这是刻意保留的，避免噪声晋级；如果觉得太慢，调 `_confidence` 的 volume/variety 权重即可，但要注意单条重复必须仍被 variety 闸门挡住。
- **话题复现是「原始提及数」统计，带轻微噪声**：`_TOPIC_NOISE` 已滤掉高频动词/副词，但像 `checker` / `working` 这类词仍可能进候选。宽窗口下靠 `MIN_ENTRIES_FOR_TOPIC=3` + `share ≥ 0.25` 两道门槛挡住，短期数据里不会误报；若要更干净，可换成词性判别或 TF-IDF，但那会引入新依赖，本轮不做。
- **情绪规则依赖用户主动填 `mood`**。不填就没有情绪信号 —— 这是数据可得性的天然边界，不是 bug（探针已验证：只填 2 篇负面时 `share=0.10`，正确地不触发）。
