"""add audit fields to policy tables

Revision ID: c0d2e4f6a8b1
Revises: f4a8c2d6e1b7
Create Date: 2026-10-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c0d2e4f6a8b1"
down_revision: Union[str, None] = "f4a8c2d6e1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("category", "sub_category", "policy_type", "policy", "audit_log")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")))
        op.add_column(table, sa.Column("created_by", sa.String(), nullable=True))
        op.add_column(table, sa.Column("updated_by", sa.String(), nullable=True))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "updated_by")
        op.drop_column(table, "created_by")
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
