# 周期报告：日报 / 周报 / 月报

## Goal

重建已退役的周期报告能力：从**日志**（唯一人工输入口）聚合出**日报 / 周报 / 月报**，
落到**已存在的** `reports` 表，并提供 API + UI。

回答用户的问题：「我这周/这个月干了什么？」

## 背景（为什么是「重建」）

- 用户问「日报 周报 月报总结还有吗」→ 核查结论：**全没了**。
- `Report` 模块整体退役：`/api/v1/reports` 与 `/reports/generate` 均 404，
  report 的 service / engine / AI 工具 / cron / UI / i18n **全部不存在**。
- **⚠️ 本仓库只有 6 个 commit，初始提交 `a444dd2` 里就已经只剩模型**——
  `api/v1/report.py`、`services/report_engine.py` 这类文件**从未进过 git**，
  **无法靠回滚恢复，只能重写**。
- **刻意保留物**（不要删）：`models/report.py` 的 `Report` / `ReportDefinition`、
  `reports` / `report_definitions` 两张表（**都是 0 行**）、`models/__init__.py` 的 import。

## 关键设计决策

### D1. 数据源只能是日志（+ 目标 + 记忆），**绝不引用 Event**
`Event` / `Report` / `Project` / `Insight` 已退役，`EventCreated` 事件链不存在了。
报告的输入面：`journals`（主）、`goals`（进度）、`memories`（本期晋级的长期认知）。

### D2. **不加表、不加列、不写迁移** —— `alembic check` 必须保持 clean
`Report` 现有字段已够用：

| 字段 | 用途 |
|---|---|
| `type` | `DAILY` / `WEEKLY` / `MONTHLY` |
| `dimension` | **复用为「领域维度」**：`ALL` 或某个 `Category`（如 `WORK`） |
| `period_start` / `period_end` | 覆盖区间（含两端） |
| `title` | 稳定标题，如「2026-09-23 日报」 |
| `summary` | 人读的叙述（**确定性模板渲染**，见 D4） |
| `content` | JSONB 结构化统计（见 D3） |
| `status` | `COMPLETED` |
| `definition_id` | 本期恒为 `NULL`（见「不做的事」） |

`dimension` 承载 `Category` 是**语义自洽**的（「按什么领域维度出的报告」），
换来的是**零 schema 变更**。

### D3. `content`（JSONB）的固定输出契约
引擎产出的**唯一**形状（前端与 AI 工具都依赖它）：

```json
{
  "period": {"start": "2026-09-17", "end": "2026-09-23", "days": 7},
  "journal_count": 12,
  "active_days": 5,
  "category_breakdown": {"WORK": 6, "LEARNING": 3, "OTHER": 3},
  "mood_breakdown": {"GOOD": 4, "NEUTRAL": 2},
  "goals": [{"id": "...", "title": "...", "category": "WORK", "progress": 40.0}],
  "memories": [{"id": "...", "content": "...", "category": "WORK"}],
  "highlights": [{"journal_id": "...", "title": "...", "excerpt": "...", "occurred_at": "..."}]
}
```

- `highlights`：本期**信息量最大**的若干条日志摘录（确定性排序，取前 N=5）。
- `category_breakdown` / `mood_breakdown`：**按计数降序、同数按 key 升序**（保证确定性）。

### D4. **引擎是确定性的（不用 LLM）**
`spec/backend/directory-structure.md` 对原引擎的定义就是
「`report_engine.py` — **pure aggregation** with a fixed output contract」。
所以 `summary` 由**模板渲染**（中/英各一套，跟 `type`/`dimension`/统计量拼），
**不调 LLM**。理由：
1. 无 API key 也能跑通
2. 可断言、不 flaky
3. 需要「会说话的总结」时，交给 **AI Copilot** 读 `content` 现场叙述（见 D7）——
   避免把会过期的 LLM 散文**存进库**

### D5. 幂等：`(user_id, type, period_start, period_end, dimension)` 唯一
- **不用** `UniqueConstraint`（那要迁移）。改在 **service 层 find-or-create**。
- 命中已存在的报告 → **原地刷新**（`updated_at` 变化），不新增行。
- **并发**：模块级 **per-user 锁**（`_LOCKS` / `_lock_for`）。
  教训来自 InsightEngine——实例级锁无效，因为每次都是新引擎实例。
- **标题必须稳定**（如「2026-09-23 日报」），**不得嵌入实时计数**，否则去重失效。

### D6. 触发方式
- **手动**：`POST /api/v1/reports/generate`
- **定时**（arq cron，走既有 `with_user` 逐用户循环）：
  - 日报：每天 00:05 生成**前一天**
  - 周报：周一 00:10 生成**上一整周**（周一~周日）
  - 月报：每月 1 日 00:15 生成**上一整月**
- **不做**「每次写日志就生成报告」——日报要等一天结束，且会重复跑。

### D7. AI 工具
`ai/tools/registry.py` 加 `query_reports`（只读），让 Copilot 能引用报告，
并**在需要时把 `content` 叙述成人话**。权限与既有只读工具一致。

### D8. 前端
- 新页面 `/reports`：类型 tab（日报/周报/月报）+ 列表 + 详情
- 详情 = 结构化统计（纯 CSS 条形，**不引图表库**——依赖里没有，且安装成本高）+ `summary` 叙述
- **入口**：侧边栏已删，所以从 **dashboard 加入口**（卡片/链接）
- i18n **zh 与 en 必须同时改**（三层回退会让残留 en 条目以英文漏出）

## Requirements

### 后端
- `app/services/report_engine.py` —— 确定性聚合引擎（D3/D4）
- `app/repositories/report_repository.py` —— `Report` 的查询（find / list / get）
- `app/schemas/common.py` —— `ReportGenerateRequest` / `ReportResponse`
- `app/api/v1/report.py` —— 4 个端点，注册进 `app/main.py`
- `app/jobs/handlers.py` + `in_process.py::REGISTRY` —— `report_generation` job
- `app/jobs/worker.py` —— 3 条 cron
- `app/core/errors.py` —— 如需新错误码（`REPORT_NOT_FOUND`）
- `app/ai/tools/registry.py` —— `query_reports`

### 前端
- `src/app/reports/page.tsx`
- `src/types/api.ts` / `src/lib/api.ts` / `src/hooks/useApi.ts`（含 `queryKeys.reports`）
- `src/lib/i18n.ts`（zh + en）
- dashboard 入口

### 文档
- `README.md` / `README.zh-CN.md` 补端点

## Constraints

1. **`alembic check` 必须 clean**（本任务**不产生任何 DDL**）
2. **不 `git commit`**（用户约定：「实现即可，提交我自己来」）
3. 时间列比较必须用 **aware** datetime（`datetime.now(timezone.utc)`），**禁止** `.replace(tzinfo=None)`
4. 日期边界用 `date`（`period_start` / `period_end` 是 `Date` 列）
5. 分层：router 只做校验 + 一次 service 调用 + `ok()`；查询只在 repository
6. 响应一律走 `{success, data, request_id}` 信封
7. 报告**只读日志/目标/记忆**，不写它们

## Out of Scope（明确不做）

- **`ReportDefinition` 自定义模板**（模型保留但不启用；`definition_id` 恒为 NULL）
- **LLM 生成 `summary`**（见 D4；由 Copilot 现场叙述替代）
- 报告导出（PDF/Markdown）
- 图表库
- 回填历史报告（只生成被请求的区间）

## Acceptance Criteria

- [ ] `ruff check app/ tests/ scripts/` 通过
- [ ] `unittest discover -s tests` 通过（新增覆盖见下）
- [ ] `scripts/smoke_test.py` 通过，且覆盖 4 个报告端点
- [ ] `alembic upgrade head` + `alembic check` → **No new upgrade operations detected**
- [ ] `npx tsc --noEmit` / `npx next lint` 通过
- [ ] 活体探针（真 uvicorn + 真 `personalos.db`）：
      生成日报 → `GET /reports` 能查到 → 详情 `content` 与 `summary` 非空
- [ ] **幂等**：同参数连续生成两次 → **不新增行**，`updated_at` 变化
- [ ] **边界**：空区间（无日志）也能生成，`journal_count=0` 且不报错
- [ ] **类型维度**：`dimension=WORK` 只统计 `category=WORK` 的日志
- [ ] 前端 `/reports` 返回 200

## 测试计划

**unittest（`tests/test_reports.py`）**
- 日报/周报/月报的**区间计算**（周一为周首；跨月/跨年的月边界）
- 幂等：二次生成不新增行
- 空区间：`journal_count=0`，`summary` 仍可渲染
- `dimension` 过滤：只统计对应 `Category`
- 统计确定性：`category_breakdown` 排序稳定

**smoke（`scripts/smoke_test.py`）**
- `POST /reports/generate` → `GET /reports` → `GET /reports/{id}` → `DELETE /reports/{id}`
- 未知 `type` → 422
- `GET /reports/{missing}` → 404

**活体**：复用 `live_probe.py` 的写法打真服务。

## Risks

| 风险 | 缓解 |
|---|---|
| 时区导致「昨天」算错 | 一律 UTC 计算 + aware datetime；`period_*` 用 `date` |
| 周首约定（周一 vs 周日） | **明确取周一**（ISO），并在测试里钉死 |
| 并发重复生成 | per-user 模块级锁（D5） |
| 空库/新用户报错 | 空区间必须能生成（见验收） |
| `dimension` 复用引起歧义 | 在 schema docstring + README 写明语义 |
