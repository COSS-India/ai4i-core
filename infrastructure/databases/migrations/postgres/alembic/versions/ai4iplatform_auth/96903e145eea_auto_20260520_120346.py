"""auto_20260520_120346

Revision ID: 96903e145eea
Revises: aca4be0874b3
Create Date: 2026-05-20 06:33:48.257811

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "96903e145eea"
down_revision: Union[str, None] = "aca4be0874b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("suspension_tag", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "suspension_tag")
