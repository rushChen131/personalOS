<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## WorkBuddy bridge

Trellis has no `--workbuddy` platform flag, and WorkBuddy does not read
`.agents/skills/`. Its two skill paths are:

- `~/.workbuddy-ai/skills/` — user level, all projects
- `.workbuddy-ai/skills/` — project level (this repo uses this one)

Project-level `.workbuddy-ai/skills` is a **Windows junction** to `.agents/skills`
(the Trellis cross-platform shared layer), so the 12 `trellis-*` skills load in
WorkBuddy without duplicating files or fighting `trellis update`.

```bash
python scripts/link_trellis_skills.py --check    # report state
python scripts/link_trellis_skills.py            # create/refresh the junction
python scripts/link_trellis_skills.py --copy     # real copies, if the junction is not picked up
python scripts/link_trellis_skills.py --unlink   # remove the bridge
```

Notes:

- A junction is **machine-local**, so it is gitignored (`.workbuddy-ai/skills`).
  Recreate it on a fresh clone with the command above.
- Skills are registered at session start — **restart WorkBuddy** after linking.
- Prefer `.agents/skills/` as the source of truth; never edit files through the
  junction expecting them to stay separate from the Trellis layer.
