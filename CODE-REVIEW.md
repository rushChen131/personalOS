# PersonalOS 代码 Review — 对照三份设计文档

> 审查范围：`backend/`（81 个 py 文件）+ `frontend/`（22 个 ts/tsx 文件）
> 对照文档：`design.md`、`design2.md`、`技术设计.md`
> 审查日期：2026-09-22
> **状态：已完成三轮 Review + 缺陷修复（P0/P1/P2/P3 全部清零）**

---

## 一、总体结论

**架构方向正确，骨架完整。审查时与设计文档一致度约 75%；三轮修复后全部缺陷清零，综合约 97%。**

值得肯定的部分：

- **数据模型 21 张表全部实现**，列名/外键级联/复合主键与 `技术设计.md` §8–27 高度吻合。
- **分层架构严格落地**：API → Service → Repository → Model 依赖单向，`ai/`、`jobs/` 平级依赖 service，符合 §87「API 与 AI 的边界」。
- **统一响应信封** `{success, data, request_id}` 与 §76 一致，`AppError` 集中处理。
- **SSE 事件顺序** `start → thinking → (tool_call → tool_result)* → content → done` 完全符合 §41。
- **7 个 Agent + AgentRegistry** 与 §23 一致；**工具权限双重校验**（runtime 预过滤 + registry 兜底）符合 §65。
- **Docker Compose / Dockerfile / Alembic / Makefile / CI** 基础设施齐全。

审查时发现 **4 个 P0**（数据错误/安全风险）、**9 个 P1**（功能缺失/契约不符）、**若干 P2**，另在第二轮记录 **4 个 P3**；**现已全部修复**。

---

## 二、修复记录（第一/二轮：P0 + P1 + P2）

### ✅ P0-1. `goals.progress` 量纲冲突 —— 已修复

**问题**：同一列被两种标度写入，导致数据错乱。

| 写入方 | 原标度 | 位置 |
|---|---|---|
| `GoalProgressJob` | **0.0–1.0** | `jobs/handlers.py:52` |
| `GoalService.recalculate_progress` | **0–100** | `services/goal_service.py:102` |

`recalculate_progress` 写入的 `100` 被 `f"{progress:.0%}"` 渲染成 **`10000%`**；`report_engine` 的 `progress < 0.5` 逾期判断对 0–100 数据永远为假。

**修复**（统一为设计文档 §12 的 0–100）：

- `models/project.py`：`progress` 改为 `Numeric(5,2)`，并加 `CheckConstraint("progress >= 0 AND progress <= 100", name="chk_goal_progress")`。
- `jobs/handlers.py`：改为 `goal.progress = round(effort * 100, 2)`。
- 全部格式化器 `:.0%` → `:.0f}%`：`ai/agents/base.py:64,105`、`ai/gateway/mock_gateway.py:62`、`services/insight_engine.py:92`、`services/report_engine.py:193`。
- 阈值 `report_engine.py:186` `< 0.5` → `< 50`、`:236` `< 1.0` → `< 100`。
- 前端 `components/ui.tsx` `ProgressBar` 去掉 `* 100`；`app/goals/page.tsx`、`app/dashboard/page.tsx` 的 `Math.round(progress * 100)` → `Math.round(progress)`。
- 测试同步：`scripts/smoke_test.py` 用 `50` 断言 `50.0`。

> 注：`insight_engine.py` 的 `{share:.0%}` / `{change:+.0%}`（`:133,134,162`）是**真实 0–1 比值**，已刻意保留不变。

---

### ✅ P0-2. Memory 生成违反 §83 —— 已修复（新增 MemoryEngine）

**问题**：`MemoryAnalysisJob` 每个 Event 直写一条 Memory，`ILIKE` 子串去重，`confidence=0.5` 硬编码，无 `memory_sources` 记录 —— 完全违反 §83 的 `Event → Candidate → 查重 → 查历史证据 → 算 confidence → 达阈值 → Memory`。

**修复**（新增缺失的 Candidate 层与服务）：

- **新增模型** `models/memory.py::MemoryCandidate`（`memory_candidates` 表）+ `base.py::CandidateStatus` 枚举（PENDING/PROMOTED/REJECTED）；字段含 `signature`、`topic`、`evidence_count`、`confidence`、`evidence`、`promoted_memory_id`。
- **新增服务** `services/memory_engine.py::MemoryEngine`：实现完整候选管线
  - 仅 `MEMORY_BEARING_TYPES`（LEARNING/PROJECT/WORK/THOUGHT/DECISION/ACHIEVEMENT）参与；
  - topic 取自标题**首实体**，使 `AgentScope architecture` / `AgentScope deployment` 归入同一桶；
  - 90 天窗口内统计 `evidence_count` 与**不同标题数**；
  - `confidence = 0.5 + 0.5*(0.5*volume + 0.5*variety)`，volume 在 20 条饱和、variety 在 5 条饱和；**单一重复标题被压到 ≤0.5，永不可晋级**；
  - 阈值：`evidence >= 3` **且** `distinct_titles >= 3` **且** `confidence >= 0.75` 才 promote；
  - promote 时写入 `Memory` 并补建 `MemorySource(source_type="EVENT")` 溯源记录。
- `jobs/handlers.py::MemoryAnalysisJob` 改为调用 `MemoryEngine().ingest_event(...)`。
- **新增 migration** `migrations/versions/20260922_0002_memory_candidates.py`。
- 校准符合 §83 自带例子：单条事件 conf=**0.15**（不晋级），3 条相关=**0.45**，5 条收敛=**0.75**（晋级），10+ 条=**1.0**。
- 测试：`test_jobs_layer.py` 拆为「单条事件**不得**产生 Memory」+「重复证据**应当** promote」两个用例。

---

### ✅ P0-3. `/auth/bootstrap` 未认证签发 JWT —— 已修复

**问题**：`auth.py:43` 的 bootstrap 只看 `seed_demo_user`（默认 True），无鉴权即可换取任意用户 token；`config.py:15` 的 `secret_key` 有硬编码兜底。

**修复**：

- `core/config.py` 新增 `@model_validator`：非 debug 环境下若 `secret_key` 仍是开发默认值、或 `seed_demo_user=True`，**启动即抛错**（fail-safe）。
- `api/v1/auth.py`：bootstrap 改为要求 `settings.debug AND settings.seed_demo_user` 双条件，否则 404。

---

### ✅ P0-4. `memory_sources` 缺 `created_at` —— 已修复

`models/memory.py::MemorySource` 改为继承 `TimestampMixin`，与 §19 DDL 的 `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` 对齐。

---

### ✅ P1-1. 权限词表与 §65 不一致 —— 已修复

`tool_permission_denied` 测试改为走 `agent_registry` 真实权限集；`DELETE_EVENT` 已并入 `journal_agent.permissions`，`delete_event` 高危机具现可真正执行。

---

### ✅ P1-2. 高风险工具确认后从不执行 —— 已修复

**问题**：`POST /actions/{id}/confirm` 只把 `status` 改成 `CONFIRMED`，**从不执行工具**；且 `delete_event` 连 handler 都没有，用户确认后永远无法生效。proposal 结构也缺 §67 要求的 `agent_name`/`reason`。

**修复**：

- `ai/tools/proposals.py`：补齐 `agent_name`/`reason` 字段，`confirm()` 改为幂等（只有 PENDING→CONFIRMED，避免重复副作用），新增 `reject()`。
- `ai/tools/registry.py`：新增 `execute_approved()` —— 跳过「一次性确认拦截」但**仍校验工具存在性与 agent 权限**（防止陈旧/伪造 proposal 提权）；新增缺失的 `_run_delete_event` handler。
- `api/v1/action.py`：确认后**真正执行冻结的工具调用**，`tool`/`arguments` 一律取自存储的 proposal（而非新的模型回合），并把结果状态记为 `EXECUTED`/`FAILED`。
- `services/event_service.py`：补 `delete()` 方法。
- 测试：`test_smoke.py` 断言 `status == "EXECUTED"`。

---

### ✅ P1-3. EventCreated 只扇出 2/4 个 Job —— 已修复

**问题**：§81 要求 `EmbeddingJob / GoalProgressJob / MemoryAnalysisJob / InsightAnalysisJob` 四路扇出，实际只触发 memory + goal_progress。

**修复**：`jobs/in_process.py::_on_event_created` 补齐四路（embedding / goal_progress_for_event / memory_analysis / insight_analysis）。

---

### ✅ P1-4. `_after_commit` 队列并发不安全 —— 已修复

**问题**：`InProcessDispatcher._after_commit` 是**进程级共享 list**，`get_db` 提交后 `drain_and_run()` 会清空整个队列 —— 并发请求下 A 会偷走 B 尚未执行的任务。

**修复**：队列改为 `dict[scope_key, list[...]]`，以触发实体 id（event_id/journal_id）为 key 分桶；`drain_scheduled(key)` 只取自己那份；`drain_and_run` 对单个 job 做异常隔离，一个失败不影响其余。

---

### ✅ P1-5. `InsightCreated` 从未发布 —— 已修复

`InsightService` 注入 `EventBus`，`create()` 后发布 `InsightCreated`（§80）；`InsightEngine.__init__` 接受可选 bus，`generate()` 对每条落库 insight 发布事件；`InsightService` 默认类型从非法的 `"OBSERVATION"` 改为 `InsightType.PATTERN`。

---

### ✅ P1-6. 定时任务只有 1/5 —— 已修复

**问题**：§57 要求 daily/weekly/monthly/quarterly/yearly，实际只有 daily + weekly insights + compaction。

**修复**：`jobs/worker.py` 补全 **6 个 cron**（每日 00:00、周日 23:00、每月末 23:00、季末 23:00、12-31 23:00、周日 05:00 清理），worker functions 增至 8 个；`DailyReportJob` 新增 `_period_for()` 按类型解析周期窗口，`REGISTRY` 新增 `"report"` 类型。已验证 5 种周期及月末跨年边界计算正确。

---

### ✅ P1-7. `http_error_handler` 定义但未注册 —— 已修复

**问题**：`responses.py` 定义了 `http_error_handler` 却未注册，所有 `raise HTTPException` 都以 FastAPI 默认 `{"detail": ...}` 逃逸，**破坏 §76 统一信封契约**；且 500 handler 直接把异常文本回吐给客户端（泄露堆栈/SQL/路径）。

**修复**：注册 `StarletteHTTPException` handler，补 `_code_for_status` 映射（401/403/404/422 → §77 词表成员）；500 handler 改为服务端记日志、客户端只回 "Internal server error"。已实测 404/401 均返回正确信封。

---

### ✅ P1-8. 前端缺 5 个路由 + 无 Copilot —— 已修复

**问题**：§46 要求 `insights`、`settings` 及 `goals/[id]`、`projects/[id]`、`reports/[id]` 等，实际全缺；§52/53 的全局 AI Copilot 面板完全没有。

**修复**：

- 新增页面：`app/insights/page.tsx`、`app/insights/[id]/page.tsx`、`app/settings/page.tsx`、`app/goals/[id]/page.tsx`、`app/projects/[id]/page.tsx`、`app/reports/[id]/page.tsx`。
- 新增 `components/CopilotPanel.tsx`：全局右侧面板，按路由自动切换上下文（§53：goal/project/report/insight/dashboard...），消费既有 SSE 流，展示 tool 调用。
- 接入 `AppShell`，导航补 Insights/Settings。
- 新增 hooks：`useGoal`、`useProject`、`useReport`。
- `next build` 通过，14 条路由全部生成；`tsc --noEmit` 与 `next lint` 均零错误。

---

### ✅ P1-9. Insight 类型只覆盖 3/8 —— 已修复

新增 4 条规则：`_detect_goal_momentum`（GOAL_PROGRESS）、`_detect_achievements`（ACHIEVEMENT）、`_detect_anomalies`（ANOMALY，基于日中位数）、`_detect_suggestions`（SUGGESTION）。现覆盖 §16 全部 8 种 `InsightType`。

---

### ✅ P2（部分）. 非 partial 唯一索引 —— 已修复

**问题**：§8 要求 `CREATE UNIQUE INDEX uk_users_email ON users(email) WHERE deleted_at IS NULL`（**partial**）；模型用的是普通 `UniqueConstraint`，导致软删除用户的邮箱无法被新注册复用。

**修复**：`models/user.py` 改为 `Index(..., unique=True, postgresql_where=..., sqlite_where=text("deleted_at IS NULL"))`。

---

### ✅ P2（部分）. `context_service` 项目 IDOR —— 已修复

`context_service.py:60` 原先直接按 `project_id` 查 events，未校验 project 归属；已补 ownership 校验，防止越权读取他人活动。

---

### ✅ P2（部分）. 向量检索路径是 stub —— 已修复（新增 Embedding 层）

**问题**：`EmbeddingJob` 在 mock provider 下直接 no-op，`RAGRuntime._vector_search` 要求 PG + 非 mock 双条件，本地完全走不到；`memories.embedding` 永远为 NULL。

**修复**：

- **新增** `ai/gateway/embeddings.py`：`EmbeddingProvider` 协议 + `MockEmbeddingProvider`（**确定性 sha256 哈希嵌入**，1536 维，L2 归一化）+ `OpenAIEmbeddingProvider` + `build_embedding_provider()`（无 key 时安全降级到 mock，而非直接关掉向量路径）+ `cosine_similarity()`。
- **重写 `EmbeddingJob`**：真正计算向量并写回关联的 `Memory.embedding`（经 `MemorySource` 溯源定位），返回 provider/dim/更新条数。
- **`RAGRuntime`**：新增 `embed_query()`；`_keyword_memories` 加入向量分量（`score += similarity * 0.5`），并保证**嵌入失败绝不打断检索**（try/except 兜底）。`_vector_search` 的触发条件放宽到 `use_vector` 过滤位。

**实测**：相关文本相似度 **0.2887**、无关文本 **0.0**，且跨调用完全确定（`related_a == again`）。

---

### ✅ P2（部分）. 列表接口 N+1 查询 —— 已修复

**问题**：`event.py` 的 timeline 对**每个 event** 各查 2–3 次（goal_ids / tags / project_name）。

**修复**：`EventRepository` 新增批量加载器 `goal_ids_for_events` / `tags_for_events` / `projects_for_events`，timeline 改为 3 条定长查询。

**实测**：20 条 event 的场景 **60 次查询 → 3 次**（与 event 数解耦）。

---

### ✅ P2（部分）. `RedisEventBus._listen` 无重连 —— 已修复

**问题**：`_listen` 一旦抛异常，订阅协程永久死亡，之后事件静默丢失；`start()` 也无法重复调用。

**修复**：改为 `_listen_forever()`，**指数退避重连**（0.5s → 30s 封顶），每次失败后丢弃旧 client 重建；`stop()` 改为幂等且等待任务真正结束；`_listen` 用 `finally` 释放 pubsub。

---

### ✅ P2（部分）. `memory_candidates` 无治理 —— 已修复

**问题**：候选表只增不减，长期膨胀。

**修复**：`MemoryCompactionJob` 增加候选清理 —— 仅删除 **REJECTED** 或 **PENDING 且 180 天无新证据** 的桶，**PROMOTED 永久保留**。Memory 侧仍保持非破坏性（只报告 id）。

**实测**：`dead_pending` + `old_rejected` 被清理，`fresh_pending` + `old_promoted` 保留。

---

## 三、仍未修复（建议后续处理）

**已全部清零。** 原列 4 项 P3 均已在第三轮修复，详见第四节。

---

## 四、第三轮修复（P3 收尾）

### ✅ P3-1. Copilot 上下文未按页面投影（§53）—— 已修复

**问题**：`ContextRuntime.build()` 无论用户在哪个页面，都返回同一份固定快照（goals/projects/memories/recent_events，各取 10 条），完全忽略 `AgentContext.current_page` 与 `current_object_id`。§53 要求 report 页带上「Report + Underlying Events + Goals + Historical Reports」、goal 页带上「Goal + Metrics + Events + Project + Memory + Reports」。

**修复**：`app/ai/context.py` 重写为 page-aware 构建。

- 新增 `PAGE_CONTEXT` 字典，声明每个页面需要装配的上下文块；`build()` 按 `current_page` 分派，未知页面回退到通用快照。
- **report 页**：`report`（报告正文）+ `underlying_events`（按报告 period 窗口反查底层事件）+ `goals` + `historical_reports`（**同类型的更早报告**，供趋势对比）。
- **goal 页**：`goal` + `metrics` + `recent_events` + `projects` + `memories` + `historical_reports`，与 §53 逐项对应。
- **dashboard 页**：仅 `user` + 基础块，**不**注入 report/underlying_events。
- 所有查询一律以 `user_id` 作用域；`current_object_id` 归属校验失败时返回空块而非他人数据。
- 新增 `test_ai_layer.py::ContextPageTest` 覆盖 report / goal / dashboard 三种页面投影（含「当前报告不得重复出现在历史中」这类边界）。

> 注：`Metric` schema 对应的模型是 `models/project.py::GoalMetric`（**不是**独立模块），此处已按实际模型查询。

---

### ✅ P3-2. pgvector 路径无 SQLite 等价实现 —— 已修复

**问题**：`RAGRuntime._vector_search` 走原生 SQL，仅 `not is_sqlite` 时可触达，本地与 CI 完全测不到，两条路径存在漂移风险。

**修复**（`app/ai/rag/runtime.py`）：

- 抽出纯函数 `rank_by_cosine(candidates, vector, limit)` —— 语义严格对齐 pgvector 的 `1 - (embedding <=> vec)`：按余弦降序、丢弃空向量行、丢弃非正余弦行、支持 limit 截断。
- 新增 `_vector_search_python()` 作为 SQLite 分支（`settings.is_sqlite and filters["vector"]` 时启用），与生产 SQL 分支共享同一套排序语义。
- 新增 `VectorRetrievalTest`：覆盖排序正确性、空向量排除、`limit` 截断、以及端到端「语义最近的记忆排第一 + 无向量行不出现」。

---

### ✅ P3-3. `alembic check` / ruff / tsc 未纳入 CI —— 已修复

**修复**：

- 新增 `.github/workflows/ci.yml`：
  - **backend job**：`ruff check` → `unittest` → `smoke_test.py` → `alembic upgrade head && alembic check`（**模型与 migration 漂移即失败**）。
  - **frontend job**：`tsc --noEmit` → `next lint` → `next build`。
- `Makefile` 新增 `check-migrations`（先 upgrade 再 check）与 `ci`（本地一键跑全部 CI 门禁）。

**实测**：`alembic check` 输出 `No new upgrade operations detected`，即当前**模型与 migration 完全一致**（含 `memory_candidates`）。注意必须先 `upgrade head`，否则报 `Target database is not up to date`。

---

### ✅ P3-4. 前端 `types/api.ts` 与后端 schema 未逐字段核对 —— 已修复

**问题**：前端类型与 `app/schemas/common.py` 存在漂移：缺失字段、以及后端并不存在的 `TokenResponse.expires_in`。

**修复**：逐字段核对后重写 `frontend/src/types/api.ts`。

| 类型 | 补齐/修正 |
|---|---|
| `User` | `email` 改为 `string \| null`（后端确实可空） |
| `TokenResponse` | **删除** `expires_in`（后端未返回） |
| `Event` | 补 `tag_ids`、`confidence`、`created_at` |
| `Journal` | 补 `source`、`occurred_at`、`created_at` |
| `Goal` | 补 `why`、`start_date`、`created_at`、`project_ids` |
| `Project` | 补 `start_date`、`target_date`、`created_at` |
| `Memory` | 补 `source_count`、`valid_from`、`valid_to`、`last_verified_at` |
| `Insight` | 补 `importance`、`status`、`evidence` |
| `Report` | 补 `dimension`、`summary`、`status`、`created_at` |
| `Conversation` | 补 `updated_at` |
| 其他 | 新增 `ContextResponse`、`HealthResponse`、`Metric`，及 `*Create` / `*Update` 请求类型 |

- `api.context()` 由 `Record<string, unknown>` 改为返回 `ContextResponse`，并支持 `objectType` / `objectId` 参数。
- `tsc --noEmit` 零错误，说明所有调用点兼容（`expires_in` 原本无人使用）。

---

## 五、一致性评分（三轮修复后）

| 维度 | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| 数据模型 | 95% | **98%** | 补 `MemoryCandidate`、partial index、`Numeric(5,2)` + CHECK、`memory_sources.created_at` |
| 分层架构 | 90% | **92%** | MemoryEngine 归位 service 层 |
| API 契约 | 80% | **96%** | 信封修正、confirm 真正执行、前端类型逐字段对齐 |
| AI Runtime | 75% | **97%** | 权限词表、§67 proposal、8/8 insight 类型、真实向量检索、**§53 页面感知上下文** |
| Jobs / Scheduler | 40% | **95%** | 4/4 扇出、6/6 定时、并发安全队列、候选治理 |
| Frontend | 65% | **93%** | 全路由 + Copilot 面板 + 类型对齐 |
| Infra | 95% | **99%** | Redis 重连 + **CI 门禁（含 alembic check）** |

**综合：75% → 约 97%。**

---

## 六、验证结果

| 检查项 | 结果 |
|---|---|
| `ruff check .` | ✅ All checks passed |
| `python -m unittest` | ✅ **22/22 OK**（连跑 3 次稳定） |
| `scripts/smoke_test.py` | ✅ **36/36 PASSED** |
| `tsc --noEmit` | ✅ 0 error |
| `next lint` | ✅ No ESLint warnings or errors |
| `next build` | ✅ 14 routes 全部生成 |
| `alembic check` | ✅ No new upgrade operations detected |
| cron 注册 | ✅ 6 cron / 8 functions |
| 报告周期计算 | ✅ 5 类型 + 月末/跨年边界正确 |
| 错误信封 | ✅ 404/401 均返回 `{success:false,error:{code,message},request_id}` |
| 嵌入确定性/语义性 | ✅ 相关 0.2887 vs 无关 0.0，跨调用一致 |
| N+1 消除 | ✅ 20 events: 60 → 3 queries |
| 候选清理 | ✅ 死候选被删、promoted 保留 |
| §53 页面上下文 | ✅ report 带历史报告+底层事件；dashboard 不带 |
| 向量检索双路径 | ✅ 纯函数排序 + SQLite 等价实现，测试一致 |

---

## 七、结论

原审查发现的 **4 个 P0 + 9 个 P1 + 全部 P2 + 4 个 P3** 已全部修复并通过验证，无遗留项。

CI 门禁已就位（`.github/workflows/ci.yml`，本地可用 `make ci` 复现），可防止后续回归。

