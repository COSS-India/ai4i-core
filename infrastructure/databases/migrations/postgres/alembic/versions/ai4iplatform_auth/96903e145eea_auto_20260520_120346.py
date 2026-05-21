"""Add users.suspension_tag for admin vs tenant suspend tracking

Revision ID: 96903e145eea
Revises: aca4be0874b3
Create Date: 2026-05-20 06:33:48.257811

Depends on aca4be0874b3 (no-op) and c4e8f1a2b3d0 (tenant status) earlier in chain.
See MIGRATION_CHAIN.md in this folder.
"""from typing import Sequence, Union

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
