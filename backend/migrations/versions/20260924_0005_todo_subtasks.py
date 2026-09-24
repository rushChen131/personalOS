"""Give todos one level of subtasks.

Revision ID: 20260924_0005
Revises: 20260924_0004
Create Date: 2026-09-24

A todo may now own one level of child todos: `parent_id` points at the parent
(NULL = top-level). The depth is capped at one level by `TodoService.create`,
because a portable self-referential CHECK cannot be expressed in SQLite.

The column carries a foreign key, and SQLite cannot `ALTER TABLE ... ADD
CONSTRAINT` — a plain `add_column` raises `NotImplementedError` from Alembic's
SQLite dialect. So this uses **batch mode**, which rebuilds `todos` and bakes the
constraint into the new `CREATE TABLE`. Only `todos` is rebuilt: the foreign keys
that `todo_metrics`, `todo_projects` and `event_todos` hold against it are left
alone, because the table name is restored before the migration ends.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260924_0005"
down_revision = "20260924_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    columns = {column["name"] for column in sa.inspect(bind).get_columns("todos")}
    if "parent_id" not in columns:
        with op.batch_alter_table("todos") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "parent_id",
                    sa.CHAR(32),
                    # Batch mode rebuilds the table, and SQLite needs every
                    # constraint to carry a name to do that — an unnamed
                    # ForeignKey raises "Constraint must have a name".
                    sa.ForeignKey(
                        "todos.id", ondelete="CASCADE", name="fk_todos_parent_id_todos"
                    ),
                    nullable=True,
                )
            )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("todos")}
    if "idx_todos_parent" not in indexes:
        op.create_index("idx_todos_parent", "todos", ["parent_id"])


def downgrade() -> None:
    bind = op.get_bind()

    # The index has to go first: SQLite refuses to drop a column that is indexed.
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("todos")}
    if "idx_todos_parent" in indexes:
        op.drop_index("idx_todos_parent", table_name="todos")

    columns = {column["name"] for column in sa.inspect(bind).get_columns("todos")}
    if "parent_id" in columns:
        with op.batch_alter_table("todos") as batch_op:
            batch_op.drop_column("parent_id")
