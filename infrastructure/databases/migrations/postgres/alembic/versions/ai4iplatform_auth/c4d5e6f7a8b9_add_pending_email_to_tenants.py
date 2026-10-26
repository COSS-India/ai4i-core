"""add pending_email to tenants

New Institution Admin email awaiting verification (AI4IDS-3401), plus when
that request's verification link expires. pending_email is EncryptedEmail
ciphertext like tenants.email, hence Text. Both nullable, no default, no
backfill — safe as a single step.

Revision ID: c4d5e6f7a8b9
Revises: 74435be97765
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "74435be97765"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("pending_email", sa.Text(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("pending_email_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "pending_email_expires_at")
    op.drop_column("tenants", "pending_email")
