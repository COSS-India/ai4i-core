"""drop pending_email from tenants

AI4IDS-3401 now changes the institution contact by picking an existing
Institution Admin (applied immediately), so the typed-email + verification
flow and its pending state (added in c4d5e6f7a8b9) are removed.

Revision ID: d5e6f7a8b9c1
Revises: 7a28dca07e9d
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c1"
down_revision: Union[str, None] = "7a28dca07e9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("tenants", "pending_email_expires_at")
    op.drop_column("tenants", "pending_email")


def downgrade() -> None:
    op.add_column("tenants", sa.Column("pending_email", sa.Text(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("pending_email_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
