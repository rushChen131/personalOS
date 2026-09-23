#!/usr/bin/env python
"""Bridge Trellis's cross-platform skill layer into WorkBuddy's skill paths.

Trellis (https://github.com/mindfold-ai/Trellis) ships a single cross-platform
shared layer at ``.agents/skills/``. WorkBuddy does NOT read that directory — it
loads skills from ``~/.workbuddy-ai/skills/`` (user level) and
``{workspace}/.workbuddy-ai/skills/`` (project level).

This script points the project-level path at the Trellis shared layer so the
``trellis-*`` skills become available in WorkBuddy, without duplicating files or
fighting ``trellis update`` (which rewrites ``.agents/skills/``).

Usage
-----
    python scripts/link_trellis_skills.py            # link (default)
    python scripts/link_trellis_skills.py --copy     # materialise real copies
    python scripts/link_trellis_skills.py --check    # report current state
    python scripts/link_trellis_skills.py --unlink   # remove the bridge

On Windows a directory *junction* is used: unlike a symlink it needs neither
elevation nor Developer Mode, and it resolves transparently for any normal
filesystem reader. On POSIX a plain directory symlink is used.

If WorkBuddy fails to see the skills through the junction (some recursive
scanners skip reparse points), re-run with ``--copy`` — it is only ~320 KB.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / ".agents" / "skills"
TARGET = REPO / ".workbuddy-ai" / "skills"


def _is_link(path: Path) -> bool:
    """True when ``path`` is a symlink or a Windows junction."""
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            # A junction is a reparse point; os.path.islink() returns False for
            # it, so check the directory attributes directly.
            return bool(os.lstat(path).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
        except (OSError, AttributeError):
            return False
    return False


def _describe(path: Path) -> str:
    if not path.exists():
        return "absent"
    if _is_link(path):
        return "link/junction"
    if path.is_dir():
        return f"directory ({len(list(path.iterdir()))} entries)"
    return "file"


def cmd_check() -> int:
    print(f"source : {SOURCE}  ->  {_describe(SOURCE)}")
    print(f"target : {TARGET}  ->  {_describe(TARGET)}")
    if not SOURCE.is_dir():
        print("\nERROR: source missing. Run `trellis init` first.", file=sys.stderr)
        return 1
    skills = sorted(p.name for p in SOURCE.iterdir() if p.is_dir())
    print(f"\ntrellis skills available ({len(skills)}):")
    for name in skills:
        print(f"  - {name}")

    if TARGET.exists():
        reachable = sorted(p.name for p in TARGET.iterdir() if p.is_dir()) if TARGET.is_dir() else []
        missing = set(skills) - set(reachable)
        print(f"\nvisible through target: {len(reachable)}")
        if missing:
            print(f"NOT visible: {sorted(missing)}")
    return 0


def _remove_target() -> None:
    if not TARGET.exists() and not _is_link(TARGET):
        return
    if _is_link(TARGET):
        # os.rmdir removes a junction/symlink to a directory without touching
        # the directory it points at.
        os.rmdir(TARGET)
    elif TARGET.is_dir():
        shutil.rmtree(TARGET)
    else:
        TARGET.unlink()


def cmd_link() -> int:
    if not SOURCE.is_dir():
        print(f"ERROR: {SOURCE} not found. Run `trellis init` first.", file=sys.stderr)
        return 1

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    _remove_target()

    if os.name == "nt":
        # mklink is a cmd *builtin*, so it must run through `cmd /c`. Use a
        # filesystem-native call instead to avoid the cmd/conhost console
        # handshake, which can throw a spurious reader-thread traceback when
        # stdout is a pipe.
        try:
            import _winapi  # type: ignore[import-not-found]

            _winapi.CreateJunction(str(SOURCE), str(TARGET))
        except ImportError:
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(TARGET), str(SOURCE)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode != 0:
                print(f"mklink failed: {result.stderr}", file=sys.stderr)
                print("Falling back to a plain copy...", file=sys.stderr)
                return cmd_copy()
    else:
        os.symlink(SOURCE, TARGET, target_is_directory=True)

    print(f"linked {TARGET} -> {SOURCE}")
    return cmd_check()


def cmd_copy() -> int:
    if not SOURCE.is_dir():
        print(f"ERROR: {SOURCE} not found. Run `trellis init` first.", file=sys.stderr)
        return 1
    _remove_target()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, TARGET)
    print(f"copied {SOURCE} -> {TARGET}")
    print("NOTE: re-run this after `trellis update` — copies do not auto-sync.")
    return cmd_check()


def cmd_unlink() -> int:
    _remove_target()
    print(f"removed {TARGET}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--copy", action="store_true", help="materialise copies instead of linking")
    group.add_argument("--check", action="store_true", help="report current state only")
    group.add_argument("--unlink", action="store_true", help="remove the bridge")
    args = parser.parse_args()

    if args.check:
        return cmd_check()
    if args.unlink:
        return cmd_unlink()
    if args.copy:
        return cmd_copy()
    return cmd_link()


if __name__ == "__main__":
    sys.exit(main())
