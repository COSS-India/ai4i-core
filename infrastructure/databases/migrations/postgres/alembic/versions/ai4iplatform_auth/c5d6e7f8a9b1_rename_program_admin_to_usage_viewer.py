"""Rename PROGRAM ADMIN role to USAGE VIEWER.

Revision ID: c5d6e7f8a9b1
Revises: b4c5d6e7f8a9
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c5d6e7f8a9b1'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

OLD_NAME = "PROGRAM ADMIN"
NEW_NAME = "USAGE VIEWER"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE roles SET name = :new WHERE name = :old"),
        {"new": NEW_NAME, "old": OLD_NAME},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE roles SET name = :old WHERE name = :new"),
        {"old": OLD_NAME, "new": NEW_NAME},
    )
