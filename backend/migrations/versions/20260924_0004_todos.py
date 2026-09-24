"""Turn goals into a todo checklist.

Revision ID: 20260924_0004
Revises: 20260923_0003
Create Date: 2026-09-24

`Goal` was a long-horizon objective: a 0-100 `progress` bar, a `goal_metrics`
child table, and a job that reverse-engineered progress from how many journal
entries mentioned the goal's title. It is now `Todo` — a checklist item whose
only completion signal is `completed_at` (NULL = open, a timestamp = done).

This is a **table copy, not a rename**. SQLite's `ALTER TABLE ... RENAME TO`
rewrites foreign keys in *other* tables for you, but Alembic's batch mode
rebuilds tables and undoes that, so the two together are hard to reason about.
Creating the new tables from the model metadata and copying every row across is
deterministic and leaves the database matching the models exactly.

Nothing is dropped before it is copied: `goals`, `goal_metrics`,
`goal_projects` and `event_goals` are all migrated, then the originals go away.
`completed_at` is derived from the old `status`/`progress` pair.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models.event import EventTodo
from app.models.project import Todo, TodoMetric, TodoProject

revision = "20260924_0004"
down_revision = "20260923_0003"
branch_labels = None
depends_on = None

#: Created from the live model metadata, so the result matches the models.
_NEW_TABLES = (
    Todo.__table__,
    TodoMetric.__table__,
    TodoProject.__table__,
    EventTodo.__table__,
)

#: Dropped last, deepest reference first.
_OLD_TABLES = ("event_goals", "goal_projects", "goal_metrics", "goals")

# The old statuses that meant "finished". Progress >= 100 was the other signal.
_DONE_STATUSES = "('DONE', 'COMPLETED', 'ARCHIVED', 'CANCELLED')"


def upgrade() -> None:
    bind = op.get_bind()
    # Snapshot before creating anything: this drives both the copy and the drop.
    existing = set(sa.inspect(bind).get_table_names())

    # 1. New tables. checkfirst keeps this safe on a database whose baseline came
    #    from current metadata (the 0001 migration uses Base.metadata.create_all).
    for table in _NEW_TABLES:
        table.create(bind, checkfirst=True)

    # 2. Copy every row across before the originals are dropped.
    if "goals" in existing:
        op.execute(
            sa.text(
                f"""
                INSERT INTO todos (
                    id, user_id, title, description, category, priority,
                    start_date, target_date, completed_at, why, metadata,
                    created_at, updated_at
                )
                SELECT
                    id, user_id, title, description, category, priority,
                    start_date, target_date,
                    CASE
                        WHEN UPPER(COALESCE(status, '')) IN {_DONE_STATUSES}
                          OR COALESCE(progress, 0) >= 100
                        THEN updated_at
                        ELSE NULL
                    END,
                    why, metadata, created_at, updated_at
                FROM goals
                """
            )
        )
    if "goal_metrics" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO todo_metrics (
                    id, todo_id, name, metric_type, current_value, target_value,
                    unit, weight, metadata, created_at, updated_at
                )
                SELECT
                    id, goal_id, name, metric_type, current_value, target_value,
                    unit, weight, metadata, created_at, updated_at
                FROM goal_metrics
                """
            )
        )
    if "goal_projects" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO todo_projects (todo_id, project_id, relation)
                SELECT goal_id, project_id, relation FROM goal_projects
                """
            )
        )
    if "event_goals" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO event_todos (event_id, todo_id, relation)
                SELECT event_id, goal_id, relation FROM event_goals
                """
            )
        )

    # 3. Only now drop the originals.
    for name in _OLD_TABLES:
        if name in existing:
            op.drop_table(name)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    # Recreate the retired schema by hand: these models are gone from the code.
    if "goals" not in existing:
        op.create_table(
            "goals",
            sa.Column("id", sa.CHAR(32), primary_key=True),
            sa.Column("user_id", sa.CHAR(32), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(32), nullable=False, server_default="OTHER"),
            sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("target_date", sa.Date(), nullable=True),
            sa.Column("progress", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("why", sa.Text(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.CheckConstraint("progress >= 0 AND progress <= 100", name="chk_goal_progress"),
        )
        op.create_index("idx_goals_user_status", "goals", ["user_id", "status"])
        op.create_index("idx_goals_target_date", "goals", ["user_id", "target_date"])
        op.create_index("idx_goals_user_category", "goals", ["user_id", "category"])

    if "goal_metrics" not in existing:
        op.create_table(
            "goal_metrics",
            sa.Column("id", sa.CHAR(32), primary_key=True),
            sa.Column("goal_id", sa.CHAR(32), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("metric_type", sa.String(32), nullable=False),
            sa.Column("current_value", sa.Float(), nullable=True),
            sa.Column("target_value", sa.Float(), nullable=True),
            sa.Column("unit", sa.String(64), nullable=True),
            sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        )
        op.create_index("idx_goal_metrics_goal", "goal_metrics", ["goal_id"])

    if "goal_projects" not in existing:
        op.create_table(
            "goal_projects",
            sa.Column("goal_id", sa.CHAR(32), primary_key=True),
            sa.Column("project_id", sa.CHAR(32), primary_key=True),
            sa.Column("relation", sa.String(32), server_default="RELATED"),
            sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )

    if "event_goals" not in existing:
        op.create_table(
            "event_goals",
            sa.Column("event_id", sa.CHAR(32), primary_key=True),
            sa.Column("goal_id", sa.CHAR(32), primary_key=True),
            sa.Column("relation", sa.String(32), server_default="RELATED"),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="CASCADE"),
        )
        op.create_index("idx_event_goals_goal", "event_goals", ["goal_id"])

    # Copy back. A finished todo is restored as progress=100 / status=ARCHIVED.
    if "todos" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO goals (
                    id, user_id, title, description, category, status, priority,
                    start_date, target_date, progress, why, metadata,
                    created_at, updated_at
                )
                SELECT
                    id, user_id, title, description, category,
                    CASE WHEN completed_at IS NULL THEN 'ACTIVE' ELSE 'ARCHIVED' END,
                    priority, start_date, target_date,
                    CASE WHEN completed_at IS NULL THEN 0 ELSE 100 END,
                    why, metadata, created_at, updated_at
                FROM todos
                """
            )
        )
    if "todo_metrics" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO goal_metrics (
                    id, goal_id, name, metric_type, current_value, target_value,
                    unit, weight, metadata, created_at, updated_at
                )
                SELECT
                    id, todo_id, name, metric_type, current_value, target_value,
                    unit, weight, metadata, created_at, updated_at
                FROM todo_metrics
                """
            )
        )
    if "todo_projects" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO goal_projects (goal_id, project_id, relation)
                SELECT todo_id, project_id, relation FROM todo_projects
                """
            )
        )
    if "event_todos" in existing:
        op.execute(
            sa.text(
                """
                INSERT INTO event_goals (event_id, goal_id, relation)
                SELECT event_id, todo_id, relation FROM event_todos
                """
            )
        )

    for table in ("event_todos", "todo_projects", "todo_metrics", "todos"):
        if table in existing:
            op.drop_table(table)
