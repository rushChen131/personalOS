"""Create the initial PersonalOS schema.

Revision ID: 20260921_0001
Revises:
Create Date: 2026-09-21

The project deliberately keeps the baseline migration dialect-aware: model
columns use native PostgreSQL UUID/pgvector where supported and SQLite-safe
representations for local development.  Future revisions must use Alembic
operations rather than changing this baseline.
"""

from __future__ import annotations

from alembic import op

from app.models import Base

revision = "20260921_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
