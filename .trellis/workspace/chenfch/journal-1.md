# Journal - chenfch (Part 1)

> AI development session journal
> Started: 2026-09-21

---



## Session 1: 洞察引擎转向日志 + WorkBuddy x Trellis 桥接

**Date**: 2026-09-23
**Task**: 洞察引擎转向日志 + WorkBuddy x Trellis 桥接
**Branch**: `main`

### Summary

InsightEngine 整文件重写为只读日志（移除 Event 依赖），修复话题复现的三处缺陷并补齐测试；把 Trellis 的 skill 层桥接进 WorkBuddy；归档 5 个任务。全程零 DDL、零 git 提交。

### Main Changes

- insight_engine.py 整文件重写：移除 Event 依赖与 _detect_investment_shift / _detect_anomalies 两条事件专属规则，改为话题复现(TREND)、情绪走向(RISK/ACHIEVEMENT)、书写频率(BEHAVIOR_CHANGE)、成果措辞(ACHIEVEMENT)等日志原生信号
- 新增 _topic_terms()：话题复现需保留条目内全部实体，_topic_key 只返回首个实体（为记忆聚桶服务），会把 'I am learning Rust ownership' 归到 learning 而非 rust
- 放宽话题复现的跨天门槛：日志常在同一个晚上连写，len(distinct_days)>=2 会滤掉真信号；改为「跨天，或单日占比>=50%」
- 修复洞察重复行竞态：模块级 per-user 锁串行化先查后插；_detect_achievements 标题改为常量（原先把实时计数写进标题，去重失效）
- 新增 _find_existing + _refresh：命中同标题时原地更新 content/confidence/evidence，替代跳过式去重，避免早期错误计数被永久冻结
- 测试：新增 4 个（reads_journals_not_events / detects_recurring_topic / detects_mood_trend_both_directions / does_not_stack_duplicate_titles），改写 stagnant_goal 为断言落库结果
- Trellis x WorkBuddy 桥接：.workbuddy-ai/skills 以 Windows junction 指向 .agents/skills，新增 scripts/link_trellis_skills.py（link/copy/check/unlink），.gitignore 忽略 junction，AGENTS.md 托管块外加说明
- 文档同步：implement.md 新增 §1.7（事件→日志信号映射表 + 四个坑）、README.md 的 InsightEngine 条目与 Event 引用块、MEMORY.md 的 InsightEngine 小节

### Git Commits

(No commits - planning session)

### Testing

- [OK] ruff check app/ tests/ scripts/ — All checks passed
- [OK] unittest discover -s tests — 43 tests OK
- [OK] scripts/smoke_test.py — PASSED 32 / FAILED 0
- [OK] alembic check — No new upgrade operations detected（零 DDL）
- [OK] tsc --noEmit 0 error / next lint clean
- [OK] 端到端：干净库 + 5 篇 Rust 日志 + 2 个 ACTIVE 目标 → 4 洞察 / 3 类型 / 0 重复

### Status

[OK] **Completed**

### Next Steps

- 重启 WorkBuddy 以注册桥接进来的 trellis-* skill；若仍不识别则跑 link_trellis_skills.py --copy
- 仓库仍全部未提交（仅 1 个 commit、5 个跟踪文件），按惯例由用户自行提交
- 09-21-backend-core 仍 in_progress，父任务 09-21-personalos-v1.2 停在 4/5
