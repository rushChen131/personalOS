# Nest one level of todos: a todo can own subtasks

## Goal

A todo can own **exactly one level** of child todos. A parent reads as "the thing",
its children as "the steps". Depth is capped at one level by design — a checklist
two levels deep stops being a checklist and starts being a project tree, and the
app already retired `Project` as a user-facing concept.

## Decisions (user-confirmed, binding)

| # | Question | Answer |
|---|---|---|
| D1 | Parent/child completion | **Independent.** A parent has its own `completed_at`; ticking it does not touch children, and an open child does not block the parent. |
| D2 | Dashboard display | **Top-level only**, with the parent row clickable to expand/collapse its children. |
| D3 | Child fields | **Title only.** A child inherits `category` and `target_date` from its parent. |
| D4 | Deleting a parent | **Cascade** — the children go with it. |

## Data model

`todos` gains one nullable self-referencing column:

- `parent_id` → `todos.id`, `ondelete="CASCADE"`, `NULL` = top-level.
- Index `idx_todos_parent` on `(parent_id)`.
- `Todo.children` / `Todo.parent` self-referential relationships;
  `children` carries `cascade="all, delete-orphan"`.

**Depth is enforced in the service, not the schema.** A portable self-referential
`CHECK` cannot be expressed in SQLite, so `create()` rejects a `parent_id` that
already points at a child.

### ⚠️ `ondelete="CASCADE"` alone is not enough

The backend never issues `PRAGMA foreign_keys=ON`, and SQLite defaults foreign
keys **off**. So the database will **not** cascade a bulk `DELETE`. Relying on the
FK alone would leave children with a dangling `parent_id`, and because
`GET /todos` returns top-level rows only, those orphans would be invisible while
still occupying rows. `TodoRepository.delete()` therefore deletes children
explicitly; the FK stays as a second line of defence for PostgreSQL.

## API contract

| Endpoint | Change |
|---|---|
| `POST /todos` | accepts optional `parent_id`. A child's `category`/`target_date` are copied from the parent and any supplied values are ignored. |
| `GET /todos` | returns **top-level todos only**, each with a `children` array. `?completed=` / `?category=` filter the top-level rows. |
| `GET /todos/{id}` | includes `children`. |
| `PUT /todos/{id}` | unchanged; `parent_id` is **not** editable (re-parenting is out of scope). |
| `DELETE /todos/{id}` | also deletes the children. |

`TodoResponse` gains `parent_id` and `children`; `TodoCreate` gains `parent_id`.

Pagination counts top-level rows, so a page of N rows can contain more than N todos.

## UI (dashboard card only)

- The list renders top-level todos; a parent with children shows a disclosure
  control and a `done/total` hint.
- Expanding reveals the children indented one level, each with its own checkbox
  and delete button.
- A parent row offers "add a step", which opens a title-only inline input.
- The existing pagination, category filter and create modal are unchanged.

## Acceptance Criteria

1. `POST /todos {"title": "x", "parent_id": "<top-level id>"}` creates a child whose
   `category`/`target_date` equal the parent's, even if different values are sent.
2. `POST /todos` with a `parent_id` that is itself a child → **400**, not a 3-deep row.
3. `POST /todos` with a `parent_id` belonging to another user → **404**.
4. `GET /todos` never returns a child as a top-level row; every child appears under
   its parent's `children`.
5. Ticking a parent does **not** change any child's `completed_at`, and vice versa (D1).
6. `DELETE` on a parent removes its children too — no row is left with a dangling
   `parent_id` (D4). This must hold with foreign keys **off**.
7. `?completed=false` returns only top-level todos whose own `completed_at IS NULL`.
8. `alembic check` stays clean; the migration upgrades and downgrades.
9. Frontend: expand/collapse works, children render indented, `tsc --noEmit` and
   `next lint` clean, zh + en keys both present.
10. The AI layer sees subtasks: `query_todos` output and the single-todo context
    block both include children.

## Notes

- Reports / insight engines keep their current flat query. Children are real rows,
  so nothing is lost; nesting them there is a separate change.
- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.

## Risks

| Risk | Mitigation |
|---|---|
| Orphaned children (FKs off) | explicit cascade delete + acceptance test 6 asserting no dangling `parent_id` |
| Depth > 1 slipping in | service guard + acceptance test 2 |
| Cross-user parent reference | ownership check inside `create()` → 404 |
| Nested payload breaking existing clients | `children` is additive; the smoke test and AI tool are updated in the same change |
