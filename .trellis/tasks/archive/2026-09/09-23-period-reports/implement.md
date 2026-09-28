# period-reports 执行记录

## 背景

`Report` 曾在「模块退役」中被摘掉 API 与 UI（模型/表保留，从未进过 git，无法回滚恢复）。本次按 PRD 的 8 条设计决策（D1–D8）**重写**，不新增任何 DDL。

## Step 1. 查询层

- `app/repositories/report_repository.py`（新增）：`create` / `get` / `find(user_id, report_type, period_start, period_end, dimension)` / `list(type, dimension, limit, offset)` / `delete`。
  排序 `period_end DESC, period_start DESC, type ASC`，保证列表顺序稳定。

## Step 2. 聚合引擎

- `app/services/report_engine.py`（新增）：确定性聚合，**不调 LLM**。
  - `period_bounds(report_type, reference)`：ISO 周（周一起）、自然月、单日；`previous_period_bounds` 取「刚结束」的那个周期。
  - `normalise_dimension()` 复用 `Category`，`ALL` 表示全生活域。
  - `content` 契约：`period{start,end,days}` / `journal_count` / `active_days` / `category_breakdown` / `mood_breakdown` / `goals[]` / `memories[]` / `highlights[]`。
  - 窗口过滤用 **aware** datetime，上界为 `end + 1 day` 的**开区间**。
  - 幂等：`async with _lock_for(user_id)` 内 find-or-create（模块级 per-user 锁）。
  - 标题**不含计数**，内容冻结则靠 `_find_existing` + 原地更新刷新。

## Step 3. API + 定时任务 + AI 工具

- `app/api/v1/report.py`（新增，前缀 `/reports`）：`GET ""`、`POST /generate`、`GET /{id}`、`DELETE /{id}`。
- `app/schemas/common.py`：`ReportGenerateRequest`（`QUARTERLY` 等不支持类型 → **422**）、`ReportResponse`。
- `app/core/errors.py`：`REPORT_NOT_FOUND`。
- `app/jobs/handlers.py`：`ReportGenerationJob`，受 `weekly_report_enabled` / `monthly_report_enabled` 开关控制，目标为**刚结束**的周期。
- `app/jobs/in_process.py`：`REGISTRY["report_generation"]`。
- `app/jobs/worker.py`：`cron_daily_report`(00:05) / `cron_weekly_report`(周一 00:10) / `cron_monthly_report`(1 日 00:15)。
- `app/ai/tools/registry.py`：新增 `query_reports`（READ）；`personal_manager` 与 `coach_agent` 挂载。

## Step 4. 前端

- `frontend/src/app/reports/page.tsx`（新增）：日报/周报/月报 tab、生成、列表 + 详情。
  - `localIso()` 用本地时区算日期（**不用** `toISOString()`），再由前端显式传给后端 —— 服务端只认 UTC，不猜本地日历。
  - `narrative()` **在前端按当前 UI 语言**渲染正文：服务端 `summary` 冻结在 `User.locale`，而语言开关从不同步到后端，直接用会中英混排。
- `types/api.ts` / `lib/api.ts` / `hooks/useApi.ts`：类型 + 4 个方法 + 3 个 hook（`queryKeys.reports`）。
- `lib/i18n.ts`：`reports.*` 与 `dashboard.viewReports`，**zh 与 en 两份都加**。
- `dashboard/page.tsx`：头部加入口（侧边栏已不存在）。

## Step 5. 顺手修掉的一个真实竞态

写测试时发现 `memory_candidates` 的 find-or-create 会在并发下抛
`UNIQUE constraint failed: memory_candidates.user_id, memory_candidates.signature`。

- **根因**：`get_db()` 在**响应之后**才 drain 任务，所以客户端连续写日志会在服务端重叠；`_ingest_statement` 的 check-then-insert 里那个 `SELECT` 看不到另一个事务正在插入的行。
- **踩过的坑**：第一版用 `session.begin_nested()` + `except IntegrityError` 想靠 SAVEPOINT 兜底 —— **不可行**。SQLAlchemy 2.0 在 savepoint 内 flush 失败时会执行
  `SessionTransaction.rollback(_capture_exception=True)`，而 `_rollback_impl` 里
  `if self._parent and _capture_exception: self._parent._rollback_exception = ...`
  会把**外层**事务标记为需要回滚 → 之后任何查询都 `PendingRollbackError`。（顺带：savepoint 回滚后实例已变成 transient，再 `session.expunge()` 反而抛 `InvalidRequestError`。）
- **最终方案**：`INSERT ... ON CONFLICT DO NOTHING`（`app/services/memory_engine.py::_get_or_create_bucket`），SQLite 与 PostgreSQL 都支持，冲突变成静默 no-op，然后重新 SELECT 采用赢家那行。**纯 Python 改动，无 DDL。**

## Step 6. 修掉 `_topic_key` 的两处分桶缺陷（用户确认「现在修，接受换桶键」）

写 Step 5 的竞态测试时顺带发现的。`_topic_key` 决定「哪些陈述会累积到同一个桶」，键错了不会当场报错，只会在很久以后表现为**晋级出错误记忆**（假合并）或**永远攒不够证据**（过度拆分）。

### 缺陷 A：含数字的实体名掉进 CJK 兜底路径

判主体用的是 `token.isascii() and token.isalpha() and len(token) > 1`，而 `isalpha()` 会否掉**任何含数字的 token**：

```
我习惯用 gpt4 写文案。   -> '我习惯用'      # 旧
我习惯用 qwen2 写文案。  -> '我习惯用'      # 旧 —— 两个不同实体并成一个桶
我喜欢用 gpt4 写文案。   -> '我喜欢用'      # 旧 —— 同一实体拆成两个桶
```

**修法**：抽出 `_is_entity_token()` —— `isascii() and len > 1 and any(ch.isalpha())`。允许数字，但仍要求**至少一个字母**，所以 `2026` 这种纯数字永远当不了主体。

### 缺陷 B（影响更大）：开场词单独成 token 时被当成主体

空格分词会把「我用 飞书 写文档」切成 `我用` / `飞书` / `写文档`。旧代码取**第一个非停用词 token** 当候选，`我用` 被 `_strip_lead` 剥成空串后又**回退成原始候选**，于是：

```
我用 飞书 写文档。   -> '我用'     # 旧
我用 微信 聊天。     -> '我用'     # 旧
我用 钉钉 打卡。     -> '我用'     # 旧 —— 所有「我用 X」全塌进一个桶
我用 C++ 写算法。    -> '我用'     # 旧
```

**修法**：改为**遍历** token，剥完还剩东西才用；剥空了就 `continue` 看下一个。（注意「我通常在周末读书」这种**没有空格**的句子本来就正常，因为 `_strip_lead` 一次性能剥到「读书」——缺陷只在分词把开场词切出来时才暴露。）

### 修复后（全部实测）

```
我喜欢用 Rust 写后端 -> rust      我喜欢用rust写后端 -> rust      I prefer Rust -> rust
我习惯用 gpt4 写文案 -> gpt4      我习惯用 qwen2 写文案 -> qwen2   我习惯用 Python3 处理数据 -> python3
我用 飞书 写文档 -> 飞书          我用 微信 聊天 -> 微信            我用 钉钉 打卡 -> 钉钉
我喜欢 -> 我喜欢（纯开场词仍有稳定桶，不丢陈述）
```

**未覆盖**：`我用 C++ 写算法` → `'c'`（`_normalize` 会把 `+` 当分隔符切掉，单字符桶不理想但已不再与无关陈述合桶）；`我用 gpt-4 写文案` → `'gpt'`（同理，`gpt-3`/`gpt-4` 会并到 `gpt`）。要彻底解决得改 `_normalize` 的切分规则，影响面大，**本次没做**。

**回归测试**：`tests/test_topic_key.py`（6 条），覆盖四种 Rust 写法同桶、含数字实体不合并/不拆分、开场词不当主体、无空格与有空格一致、纯开场词不丢。
**测试有牙齿的证明**：把旧逻辑原样重实现后重跑这些断言，**16 条里挂 9 条**；新逻辑 **0 挂**。

## 验证（Step 1–6 全部完成后重跑）

后端（`backend/.venv/Scripts/python.exe`）：

| 检查 | 结果 |
|---|---|
| `ruff check app/ tests/ scripts/` | All checks passed |
| `unittest discover -s tests` | **68 tests OK**（原 60 + 2 竞态 + 6 分桶） |
| `scripts/smoke_test.py` | **62 PASSED / 0 FAILED** |
| `alembic upgrade head` + `alembic check` | No new upgrade operations detected |

前端：

| 检查 | 结果 |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx next lint` | No ESLint warnings or errors |
| `GET /reports`（dev server） | **200**，13 021 B（对照 `/journals` 13 029、`/dashboard` 13 039；伪路由 404 / 12 528 B） |

真实 uvicorn（:8000，真 DB、真网络）：

| 探针 | 结果 |
|---|---|
| `report_probe.py`（报告全流程） | **29 PASSED / 0 FAILED** |
| `live_probe.py`（路由 + category 过滤） | **18 PASSED / 0 FAILED** |
| `live_burst.py`（8 路并发写同一主题） | 8/8 → 200，**1 个桶**，`evidence_count=8`，PROMOTED |
| 服务端日志 | 无 `IntegrityError` / `Traceback` / `level=error` |

## 换桶键的副作用（**未清理，等用户决定**）

改 `_topic_key` 会变更桶键，库里旧键的桶**从此收不到新证据**（不可能再晋级，最终被 `MemoryCompactionJob` 按 200 天窗口清掉），属**惰性残留**。真库（dev）里当前有：

- 4 个「动词短语」桶：`我喜欢用` / `我习惯用` / `我偏好` / `我一直在用`，各 `evidence_count=5`、`confidence=0.71`（**卡在 0.75 门槛下**）。其 `evidence.statements` 全是**本轮探针**的 `racecase*` / `liveburst*` 语句；`我喜欢用` 桶 `created_at=2026-09-22 08:51`，是**更早版本的 `_topic_key`** 建的。
- 另有 `rust` 桶带着**旧 evidence schema** `{"titles": ["rust"]}`（当前 schema 是 `{"statements": [...], "source_journal_ids": [...], "category": ...}`）—— 说明 dev 库里还留着 **2026-09-22 重写之前**的行。

**这些都在 dev 库、且全是探针/历史残留，没有删**（删库属数据操作，需用户确认）。

