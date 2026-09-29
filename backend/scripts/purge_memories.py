"""Delete memories from the dev database.

Run from backend/:
    .venv/Scripts/python.exe scripts/purge_memories.py           # dry run
    .venv/Scripts/python.exe scripts/purge_memories.py --apply

Memories are derived rather than authored, so the only way to get rid of a bad
one -- probe residue, or junk distilled from journals that have since been
deleted -- is to delete it. The UI delete button does the same thing one row at
a time; this is for clearing a whole database.

It goes through ``MemoryService.delete``, the same code path as
``DELETE /memories/{id}``, rather than raw SQL, so the edges SQLite will not
cascade (``memory_sources``, ``memory_candidates.promoted_memory_id``) are cut
exactly as they are in production.

Dry run by default: this is destructive and there is no undo. Take a copy of
``personalos.db`` first -- ``cp personalos.db personalos.db.bak-$(date +%Y%m%d-%H%M%S)``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.infrastructure.bus.event_bus import event_bus  # noqa: E402
from app.models.memory import Memory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.memory_repository import MemoryRepository  # noqa: E402
from app.services.memory_service import MemoryService  # noqa: E402

DEMO_EMAIL = "demo@personalos.local"


async def main(apply: bool, email: str) -> int:
    service = MemoryService(MemoryRepository(), event_bus)
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"no user with email {email}", file=sys.stderr)
            return 1

        memories = list(
            (await session.scalars(select(Memory).where(Memory.user_id == user.id))).unique()
        )
        print(f"user {email}: {len(memories)} memories")
        for memory in memories:
            print(f"  {memory.id}  {memory.type:<12} {str(memory.content)[:48]!r}")

        if not apply:
            print("\ndry run -- nothing deleted. Re-run with --apply.")
            return 0

        removed = 0
        for memory in memories:
            if await service.delete(session, user.id, str(memory.id)):
                removed += 1
        # The repository only flushes, so the commit belongs here -- exactly as
        # ``get_db`` would do it after the response in the API path.
        await session.commit()
        print(f"\ndeleted {removed} memories")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete memories from the dev database.")
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    parser.add_argument("--email", default=DEMO_EMAIL, help=f"account to purge (default: {DEMO_EMAIL})")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply, args.email)))
