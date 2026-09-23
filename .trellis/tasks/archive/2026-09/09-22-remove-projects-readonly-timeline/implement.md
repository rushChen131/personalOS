# Implement — 移除项目模块 + 时间线改为只读

## Result

Done. All acceptance criteria in `prd.md` met. **No DDL change** — `alembic check` remains clean.

## Order of work

1. **Backend surface first** (so the frontend has nothing to call).
   - `main.py`: dropped the `project` import + `include_router(project.router)`.
   - Deleted `app/api/v1/project.py`, `app/services/project_service.py`.
   - Deleted `ProjectRepository` from `app/repositories/goal_repository.py` (it was the last class in the file; truncating at `class ProjectRepository:` was enough).
   - `errors.py`: dropped `PROJECT_NOT_FOUND`.
   - `schemas/common.py`: dropped `ProjectCreate/ProjectUpdate/ProjectResponse`, `EventCreate.project_id`, `GoalCreate/GoalResponse.project_ids`, `ContextResponse.related_projects`.
   - `context_service.py`: removed the `object_type == "project"` branch, the goal→projects lookup, and the `related_projects` output.
   - `goal_repository.py` / `goal_service.py`: removed `attach_projects`, `list_project_ids`, `get_project`.
   - `event_service.py` / `event.py`: dropped the `project_id` write and the `project_id` list filter; timeline now emits `project_name=None`.

2. **AI layer.**
   - `tools/registry.py`: removed the `query_projects` ToolDefinition, `_run_query_projects`, and the `project_id` property from the `create_event` schema + its call site.
   - `agents/base.py`: removed `query_projects` from all four tool lists; dropped the `projects` render branch in `PersonalManagerAgent.compose`; fixed `JournalAgent.system_prompt`'s JSON contract; reworded `CoachAgent`'s canned suggestion.
   - `context.py`: dropped the `project`/`projects` `PAGE_CONTEXT` entries, the two dispatch lines, `_project_block`, `_projects`, and `projects` from the unknown-page fallback tuple.
   - `mock_gateway.py`: dropped the `projects` branch in `synthesize()`, the project entry in `plan()`'s `specific` tuple, and the "and projects" phrasing in `compose()`.

3. **Frontend.**
   - `rm -rf src/app/projects`.
   - `AppShell.tsx` NAV, `CopilotPanel.tsx` context branch.
   - `lib/api.ts`, `hooks/useApi.ts`, `types/api.ts` (incl. `Project`/`ProjectCreate`/`ProjectUpdate`).
   - `lib/i18n.ts`: 26 lines removed across **both** zh and en dictionaries.

4. **Timeline → read-only.**
   - Rewrote `timeline/page.tsx` without the form, `EVENT_TYPES`, local state, or `useCreateEvent`.
   - Added `timeline.emptyLogViaCopilot`; removed the seven form-only `timeline.*` keys from both dictionaries.

5. **Tests.**
   - `test_smoke.py`: projects block → asserts `/api/v1/projects` **404**; event creation no longer passes `project_id`.
   - `test_ai_layer.py`: `READ_TOOLS` without `query_projects`; goal-context test no longer expects a `projects` key; renamed to `..._includes_metrics_and_related_blocks`.
   - `scripts/smoke_test.py`: the `[projects]` section became `[projects removed]`, asserting 404 on GET and POST.

## Gotchas hit

- **`tsc --noEmit` after deleting a route**: `.next/types/app/projects/page.ts` lingered and broke the typecheck. Fixed by deleting **only** `.next/types/app/projects` — do NOT `rm -rf .next` while the dev server is live.
- **Multi-line `str.replace` silently no-ops** on files with a BOM/CRLF (`context.py`, `goal_service.py`). Used `Read` + `Edit` for those instead.
- A first edit to `schemas/common.py` accidentally **duplicated** the Project schema block; ruff's `F811 Redefinition` caught it. Removed by line-range splice.

## Verification

| Gate | Result |
| --- | --- |
| `ruff check app tests scripts` | All checks passed! |
| `unittest` | **43/43** |
| `scripts/smoke_test.py` | **34/34** |
| `tsc --noEmit` | 0 error |
| `next lint` | clean |
| `alembic check` | No new upgrade operations detected |
| Backend `/health` | 200 |
| `/api/v1/projects` | 404 |
| Frontend routes | 10/10 200, `/projects` 404 |
| DB tables/columns | `projects`, `goal_projects`, `events.project_id` all present |

Copilot end-to-end (SSE) verified across all agent routes; 「我今天学了2小时Rust」 creates a LEARNING event via `journal_agent`.
