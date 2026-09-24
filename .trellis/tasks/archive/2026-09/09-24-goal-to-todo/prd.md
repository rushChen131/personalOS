# goal-to-todo：把「目标」改成待办清单

## 背景

`Goal` 目前是一个**带进度条的长周期目标**：`progress`（0–100，有 CHECK 约束）、
`GoalMetric` 子表（current/target 值）、`GoalProgressJob` 按「日志里提到目标标题的篇数」
反推进度（20 篇 = 100%）。面向用户只有 dashboard 上一张卡片，**没有独立页面**。

用户要求**把它改成 todolist**，并确认了四条口径：

| 决策 | 用户选择 |
|---|---|
| 改动深度 | **全链路改名成 todo**（模型类、表名、接口路径） |
| 进度与指标 | **去掉进度，但记录完成时间**（新增 `completed_at` + 迁移） |
| 待办字段 | **分类**（`category`）；完成勾选是核心，默认包含 |
| 页面 | **只改 dashboard 卡片**，不新建路由 |

## 目标形态

一条待办 = **`title` + `category` + 完成态**。完成态由 `completed_at` 表达：

- `completed_at IS NULL` → 未完成
- `completed_at` 有值 → 已完成，且该值就是完成时刻

这比「`status` 字符串 + `progress` 百分比」更难写错：只有一个真相来源，不可能出现
「status=ACTIVE 但 progress=100」这种自相矛盾的行。

## 设计决策

**D1. 命名全线改掉，不留 `Goal` 词汇。**
`Goal`→`Todo`、`GoalMetric`→`TodoMetric`、`GoalProject`→`TodoProject`、
`EventGoal`→`EventTodo`；表 `goals`→`todos`、`goal_metrics`→`todo_metrics`、
`goal_projects`→`todo_projects`、`event_goals`→`event_todos`；
接口 `/goals`→`/todos`；`GOAL_NOT_FOUND`→`TODO_NOT_FOUND`；
AI 工具 `query_goals`→`query_todos`；Agent `goal_agent`→`todo_agent`。

**D2. 迁移用「建新表 + 搬数据 + 删旧表」，不用 `rename_table`。**
SQLite 上 `ALTER TABLE RENAME` 会自动改写别的表的 FK 引用，而 alembic 的 batch 模式
重建表又会把这个好处抵消掉 —— 两者叠加行为难预测。显式建表/搬数据/删表是**确定性的**，
且迁移跑完 DB 与模型必然一致，`alembic check` 必 clean。
**四张表的数据全部搬过去，不丢数据**（含 `goal_metrics` 的行）。

**D3. `completed_at` 由旧数据推导。**
`status` 里含 `DONE`/`COMPLETED`/`ARCHIVED`，或 `progress >= 100` → `completed_at = updated_at`；
否则 `NULL`。旧 `status`/`progress` 两列随旧表一起消失。

**D4. 保留 `description` / `why` / `priority` / `start_date` / `target_date` 列。**
用户这次只要 `title + category + 完成态`，但删列是不可逆的、且这几列是既有契约
（`target_date` 对「待办」天然有用）。**只删用户明确要求删的 `progress` 与随之冗余的 `status`**，
其余列保留但不暴露在 UI 上。这是本项目一贯的口径：能删的是代码入口与 UI，不是历史契约。

**D5. `GoalProgressJob` 整个删掉，不只是停用。**
进度没了，这个 job 的输出就没有落点了。同时从 `REGISTRY` 与 `JournalCreated` 扇出里摘掉，
`ai/runtime/base.py` 的 `goal_ids` 字段一并删除。`MemoryCompactionJob` 等其余 job 不动。

**D6. `GoalMetric` 的 API 入口删掉，模型与表保留。**
`POST /goals/{id}/metrics`、`MetricCreate`、`MetricResponse`、`GoalService.add_metric`、
`recalculate_progress` 全部移除；`TodoMetric` 模型与 `todo_metrics` 表保留
（与 `Report` / `Insight` / `Event` 的退役口径一致）。

**D7. dashboard 卡片改成可勾选的待办列表。**
勾选 → `PUT /todos/{id}` 带 `completed_at`（前端传当前时间）或 `completed=false` 清空。
保留分页（卡片高度固定）。**不新建 `/todos` 路由**。

**D8. 报告里的「涉及目标」改成「涉及待办」。**
`ReportEngine.content` 的 `goals` 键改名 `todos`，键内不再有 `progress`，改带 `completed`。
服务端 `summary` 与前端 `narrative()` 的中英文案同步改。

## 不在本次范围

- 新建 `/todos` 独立页面（用户明确不要）
- 截止日期的 UI（列保留，不暴露）
- 子任务 / 重复任务 / 提醒 / 排序拖拽
- 删除 `Report` / `Insight` / `Event` / `Project` 等已退役模块的表

## 验收标准

1. `GET/POST /todos`、`GET/PUT/DELETE /todos/{id}` 全部可用；`/goals` 返回 **404**。
2. `POST /todos` 只接受 `title` / `category`（+ 可选的保留列），响应含 `completed_at`。
3. `PUT /todos/{id}` 能把 `completed_at` 置为时间（完成）或置 `null`（重开）。
4. 待办可带 `?category=` 过滤；未知 category → **422**。
5. 迁移后 `alembic check` → **No new upgrade operations detected**。
6. 迁移后旧数据仍在：`todos` 行数 ≥ 迁移前 `goals` 行数，且 title/category 一致。
7. 代码库里除迁移文件与 `.trellis` 文档外，**不再有 `Goal` / `goal` 标识符**
   （保留列名/退役模型除外 —— 见 D4/D6）。
8. 日志写入**不再**触发 `goal_progress` job。
9. AI 工具 `query_todos` 可用；问「最近有什么待办」时 mock gateway 路由到它。
10. 报告 `content.todos` 存在且不再含 `progress`；中英 summary 都提到「待办 / todos」。
11. dashboard 卡片能新增、勾选完成、取消完成、删除。
12. 全量门禁通过：`ruff`、`unittest discover`、`smoke_test.py`、`alembic check`、
    `tsc --noEmit`、`next lint`。

## 风险

| 风险 | 应对 |
|---|---|
| 迁移删表 → 数据丢失 | 先建新表并**全量搬运**，再删旧表；迁移里断言搬运行数一致 |
| 改名漏点（本项目最易漏的是 `jobs/worker.py` 按字符串引用的 job type、`ai/rag/runtime.py` 的检索分支、`ai/context.py` 的 PAGE_CONTEXT、`mock_gateway` 的 plan/synthesize） | 全仓库 grep `goal` 逐条销账，最终以「验收标准 7」收口 |
| 前端 i18n 只改一半（三层回退会让残留 en 条目以英文漏出） | zh 与 en 两个字典必须同时改 |
| `User.goals` / `Event.goals` / `Project.goals` 三个 relationship 漏改 → mapper 配置期抛错 | 一并改，并跑 `unittest` 触发 mapper 配置 |
