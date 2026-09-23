"""Clear all business data for a PersonalOS deployment, keeping user accounts.

The API deliberately exposes DELETE only for journals and goals, so a full wipe
cannot be driven over HTTP. This script goes through the ORM instead, which also
gives us correct foreign-key ordering and a per-table report of what was removed.

    cd backend && .venv/Scripts/python.exe scripts/reset_data.py --dry-run
    cd backend && .venv/Scripts/python.exe scripts/reset_data.py

Options:
    --dry-run        report row counts only, delete nothing
    --keep-agents    also keep agent_runs / tool_runs audit history
    --yes            skip the interactive confirmation prompt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `python scripts/reset_data.py` from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AgentRun,
    Conversation,
    Event,
    EventGoal,
    EventTag,
    Goal,
    GoalMetric,
    GoalProject,
    Insight,
    Job,
    Journal,
    Memory,
    MemoryCandidate,
    MemorySource,
    Message,
    Project,
    Report,
    ReportDefinition,
    Tag,
    ToolRun,
)

# Delete children before parents so foreign keys never block the wipe.
# `users` and `user_settings` are intentionally absent — the account is kept.
BUSINESS_TABLES = [
    ("memory_sources", MemorySource),
    ("memory_candidates", MemoryCandidate),
    ("memories", Memory),
    ("event_tags", EventTag),
    ("event_goals", EventGoal),
    ("events", Event),
    ("goal_metrics", GoalMetric),
    ("goal_projects", GoalProject),
    ("goals", Goal),
    ("projects", Project),
    ("tags", Tag),
    ("insights", Insight),
    ("reports", Report),
    ("report_definitions", ReportDefinition),
    ("journals", Journal),
    ("messages", Message),
    ("conversations", Conversation),
    ("jobs", Job),
]

# Audit logs are wiped too by default — they reference deleted events/agents and
# would otherwise linger as orphans. `--keep-agents` preserves them.
AGENT_TABLES = [
    ("tool_runs", ToolRun),
    ("agent_runs", AgentRun),
]


async def count_rows(session: AsyncSession, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def clear(dry_run: bool, keep_agents: bool, assume_yes: bool) -> int:
    targets = list(BUSINESS_TABLES) + ([] if keep_agents else AGENT_TABLES)

    async with SessionLocal() as session:
        # --- survey ---------------------------------------------------------
        counts: dict[str, int] = {}
        for name, model in targets:
            counts[name] = await count_rows(session, model)

        total = sum(counts.values())
        print("\nRows to delete:")
        for name, _ in targets:
            marker = "" if counts[name] else "   (empty)"
            print(f"  {counts[name]:>6}  {name}{marker}")
        print(f"  {'-' * 6}")
        print(f"  {total:>6}  TOTAL\n")

        if keep_agents:
            kept = await count_rows(session, AgentRun)
            print(f"Keeping {kept} agent_runs rows (--keep-agents).\n")

        if total == 0:
            print("Nothing to delete — database is already clean.")
            return 0

        if dry_run:
            print("Dry run: no rows were deleted.")
            return 0

        if not assume_yes:
            try:
                answer = input(f"Delete {total} rows from {len(targets)} tables? [y/N] ").strip().lower()
            except EOFError:
                answer = ""
            if answer not in {"y", "yes"}:
                print("Aborted — nothing was deleted.")
                return 1

        # --- delete ---------------------------------------------------------
        deleted: dict[str, int] = {}
        for name, model in targets:
            result = await session.execute(delete(model))
            deleted[name] = result.rowcount or 0
        await session.commit()

        print("\nDeleted:")
        for name, _ in targets:
            print(f"  {deleted[name]:>6}  {name}")
        print(f"\nDone. {sum(deleted.values())} rows removed; user accounts preserved.")

    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Clear PersonalOS business data, keeping accounts.")
    parser.add_argument("--dry-run", action="store_true", help="report counts but delete nothing")
    parser.add_argument("--keep-agents", action="store_true", help="keep agent_runs / tool_runs audit rows")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()

    try:
        code = await clear(dry_run=args.dry_run, keep_agents=args.keep_agents, assume_yes=args.yes)
    finally:
        # Dispose the pool so the script exits cleanly on Windows.
        await engine.dispose()
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
