"""Add memory_candidates for the §83 Event -> Candidate -> Memory pipeline.

Revision ID: 20260922_0002
Revises: 20260921_0001
Create Date: 2026-09-22
"""

from __future__ import annotations

from alembic import op

from app.models import Base
from app.models.memory import MemoryCandidate

revision = "20260922_0002"
down_revision = "20260921_0001"
branch_labels = None
depends_on = None

_TABLE = MemoryCandidate.__table__


def upgrade() -> None:
    # create_all with checkfirst is safe on both SQLite and PostgreSQL and
    # skips the tables the baseline migration already created.
    Base.metadata.create_all(bind=op.get_bind(), tables=[_TABLE], checkfirst=True)


def downgrade() -> None:
    _TABLE.drop(bind=op.get_bind(), checkfirst=True)
