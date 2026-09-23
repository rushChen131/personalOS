# backend-jobs 执行计划

## Step 1. EventBus
- `app/infrastructure/bus/` 内存实现 + Redis 适配（redis 不可用时退回内存）
- app 启动时注册订阅

## Step 2. Journal→Event 链
- JournalService.create 后 pub JournalCreated → handler 调 JournalAgent → 生成候选事件 → 存 proposals（用户确认流程接口）
- `POST /events` 后 pub EventCreated → 触发 jobs

## Step 3. EmbejJob + GoalProgressJob
- EventCreated handler：更新关联 goal progress（sum duration by goal）；生成 memory candidates（关键词关联已有 memory / 新 candidate）

## Step 4. InsightEngine
- 规则：时间投入突变、目标停滞(no events in N days)、项目并发数
- InsightCandidate → confidence 过滤 → 落库 insights（含 evidence JSON）

## Step 5. ReportEngine
- 聚合：events stats by type/period；goals progress；top projects；memories top
- 无 key：规则生成文本 summary + 各 section
- 有 key：调 report_agent 生成文字，聚合数字仍走统计
- 注册 `POST /api/v1/reports/generate`（同步版）与 `POST /api/v1/reports/generate?async=false`

## Step 6. Worker
- `jobs/worker.py` arq；`jobs/in_process.py` 手动 trigger
- 定时注释：daily 00:00, weekly Sun 23:00, monthly last day

## Step 7. 验证
- 走通 Journal→Event→GoalProgress→Memory 链
- report generate 产出 Report JSON
- insight 生成 RISK 记录
- ruff check