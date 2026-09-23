# 移除项目模块 + 时间线改为只读

## Goal

PersonalOS 的「项目（Project）」模块实际使用率极低，却把 `Event`、`Goal`、上下文投影、报告聚合、AI 工具层全部耦合了进去，带来持续的维护成本与认知负担。本任务把这个模块从**前后端代码中彻底移除**（数据库表与已有数据保留），并把「时间线」页面从「录入 + 浏览」改为**纯只读的回顾视图** —— 事件统一改由 Copilot 对话创建。

## Requirements

### R1 — 移除项目模块（前端）

- 删除路由 `/projects` 与 `/projects/[id]`（含目录）。
- `AppShell.tsx` 的 `NAV` 数组移除 `/projects` 导航项。
- `CopilotPanel.tsx` 的 `useContextTarget()` 移除 `pathname.startsWith("/projects")` 分支。
- `hooks/useApi.ts` 移除 `useProjects` / `useProject` / `useCreateProject`；`queryKeys.projects` 一并移除。
- `lib/api.ts` 移除 `listProjects` / `createProject` / `getProject`。
- `types/api.ts` 移除 `Project` / `ProjectCreate` / `ProjectUpdate`，以及**仅供项目模块使用**的字段（见 N1）。
- `lib/i18n.ts` 移除 `nav.projects` / `projects.*` / `copilot.ctx.project(s)` 的 zh + en 两套文案。

### R2 — 移除项目模块（后端）

- 删除 `app/api/v1/project.py`，并从 `app/main.py` 摘掉 `project` 路由注册与 import。
- 删除 `app/services/project_service.py`。
- 删除 `ProjectRepository`（位于 `app/repositories/goal_repository.py`）。
- 删除 `app/schemas/common.py` 中的 `ProjectCreate` / `ProjectUpdate` / `ProjectResponse`，以及 `GoalContext` 的 `related_projects` 字段。
- `app/core/errors.py` 移除 `PROJECT_NOT_FOUND`。
- 删除 AI 工具 `query_projects`（`app/ai/tools/registry.py` 的 `ToolDefinition` + `_run_query_projects`），并从各 agent 的 `tools` 列表移除；`create_event` 工具的 `project_id` 入参一并移除。
- `app/ai/context.py` 移除 `project` / `projects` 页面投影块与 `_project_block` / `_projects`；`PAGE_CONTEXT` 相应调整。
- 事件/目标/报告链路移除项目关联（见 N1 的保留清单）。

### R3 — 时间线改为只读

- `app/timeline/page.tsx` 移除「记录事件」`Card`（`timeline.logEvent` 表单），页面只保留：页头 + 事件列表 + 按日期分组。
- 移除随之无用的状态（`title` / `type` / `minutes`）与 `useCreateEvent` 调用。
- 时间线不再依赖任何创建入口；空态文案需引导用户去 Copilot 创建（而非「在上方记录第一条」）。

### R4 — 事件创建统一走 Copilot

- 事件创建唯一入口是 Copilot 对话（`personal_manager` agent 的 `create_event` 工具）。
- 需验证中文自然语言录入链路仍然正常（如「我学了2小时Rust」→ 创建 LEARNING 事件）。

## Acceptance Criteria

- [ ] `frontend/src/app/projects/` 目录已删除。
- [ ] 侧边栏无「项目」入口；`/projects` 返回 404。
- [ ] 前端 `grep -ri project src/` 无残留引用（仅允许 `Event` 上保留的字段，见 N1）。
- [ ] `backend/app/api/v1/project.py`、`services/project_service.py` 已删除；`ProjectRepository` 已删除。
- [ ] `/api/v1/projects` 返回 404。
- [ ] AI 工具层无 `query_projects`；所有 agent 的 `tools` 列表不再含它。
- [ ] 时间线页面无任何表单/输入框，仅有列表与分组。
- [ ] `ruff check` clean。
- [ ] `unittest` 全绿（含为本次改动调整后的用例）。
- [ ] `tsc --noEmit` 0 error；`next lint` clean。
- [ ] `alembic check` clean（**必须无 DDL 变更**）。
- [ ] smoke 测试通过（已移除 projects 相关断言）。
- [ ] 后端 health 200；前端全部保留路由 200。

## Notes

### N1 — 数据层保留清单（**不删列、不删表**）

本次是**代码层移除**，数据库 schema 完全不动，因此 `alembic check` 必须保持 clean。

以下是「物理保留、但代码层可能需要保留读写」的项 —— **实现时按此判断，不要擅自删列**：

| 项 | 处理 |
| --- | --- |
| `projects` 表 | **保留**（数据不丢） |
| `goal_projects` 关联表 | **保留** |
| `Event.project_id` 列 | **保留**（列还在，但不再有入口写入） |
| `Goal` ↔ `Project` 关系 | **保留在模型层**（删关系会牵动 mapper 配置） |
| `Project` 模型类 | **保留**（被 `models/base.py` / `user.py` 的关系引用；删了会破坏 mapper） |
| `EventCreate.project_id` 入参 | **移除**（前端与 API 都不再接受） |
| `TimelineItem.project_id` / `project_name` | **保留**（历史数据可能仍有值，前端不展示即可） |
| `StatsResponse.by_project` | **保留**（聚合逻辑不动，前端不展示） |
| `report` payload 的 `projects` 键 | **保留**（报告 JSON 契约，见 `report_service.py` 注释） |
| `Event.project_id` 的过滤查询参数 | **保留**（无害；去掉要动 repo 签名，收益低） |

> 一句话原则：**能删的是「代码入口与 UI」，不能删的是「模型/表/历史契约」。**

### N2 — 为什么 `Project` 模型不能删

`app/models/user.py` 有 `projects` 关系，`app/models/event.py` 有 `project` 关系，`app/models/project.py` 有 `Goal` 与 `Project` 的 `secondary="goal_projects"` 双向关系。SQLAlchemy 的 mapper 在配置期会解析这些字符串，**删掉 `Project` 类会导致 `event.py` / `user.py` 的 relationship 解析失败**（`InvalidRequestError`）。因此模型层整体保留。

### N3 — 与 `insight_engine` / `memory_engine` 无关

`memory_engine.py` 里的 `"PROJECT"` 是**事件类型枚举值**（`EventType.PROJECT`），不是项目实体引用，**不要删**。

### N4 — i18n

移除文案时必须 **zh 与 en 两个字典同时删**，否则 `translate()` 会触发三层回退（当前语言 → en → key），残留的 en 条目会以英文形式漏出。

### N5 — 其它平台约束

- 保持「只实现，不 git commit」。
- 不要动 `frontend/.next` 与 dev server：验证前端改动用 `tsc --noEmit` + `next lint`，**不要在 dev 运行时跑 `npm run build`**。
