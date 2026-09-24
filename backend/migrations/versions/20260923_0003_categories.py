"""Add a life-domain category to journals, goals and memories.

Revision ID: 20260923_0003
Revises: 20260922_0002
Create Date: 2026-09-23

All three tables share one vocabulary (投资、工作、学习…) so a domain can group
entries across modules. Existing rows predate the field and are filed under
OTHER, which is why the column is NOT NULL with a server default rather than
nullable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260923_0003"
down_revision = "20260922_0002"
branch_labels = None
depends_on = None

_TABLES = ("journals", "goals", "memories")


def _index_name(table: str) -> str:
    return f"idx_{table}_user_category"


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "category",
                sa.String(length=32),
                nullable=False,
                server_default="OTHER",
            ),
        )
        op.create_index(_index_name(table), table, ["user_id", "category"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(_index_name(table), table_name=table)
        # SQLite cannot drop a column in place, so go through batch mode.
        with op.batch_alter_table(table) as batch:
            batch.drop_column("category")
