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

_TABLES = ("category", "sub_category", "policy_type", "policy")


def _add_column_if_not_exists(table: str, column: str, ddl: str) -> None:
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")


def upgrade() -> None:
    for table in _TABLES:
        _add_column_if_not_exists(table, "created_at", "TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL")
        _add_column_if_not_exists(table, "updated_at", "TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL")
        _add_column_if_not_exists(table, "created_by", "VARCHAR")
        _add_column_if_not_exists(table, "updated_by", "VARCHAR")
    # audit_log is append-only so it only needs created_at / created_by
    _add_column_if_not_exists("audit_log", "created_at", "TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL")
    _add_column_if_not_exists("audit_log", "created_by", "VARCHAR")


def downgrade() -> None:
    op.drop_column("audit_log", "created_by")
    op.drop_column("audit_log", "created_at")
    for table in reversed(_TABLES):
        op.drop_column(table, "updated_by")
        op.drop_column(table, "created_by")
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
