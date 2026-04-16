"""Materialize tenant columns on users table.

Rename tenant_id_cached to tenant_id, add tenant_status and user_status columns.
Eliminates the need for cross-DB lookups to the multi-tenant database at runtime.

Revision ID: a1b2c3d4e5f6
Revises: 81aa5feb3b29
Create Date: 2026-04-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "81aa5feb3b29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename tenant_id_cached → tenant_id
    op.alter_column("users", "tenant_id_cached", new_column_name="tenant_id")
    # Index already exists as ix_users_tenant_id_cached — rename it
    op.execute("ALTER INDEX IF EXISTS ix_users_tenant_id_cached RENAME TO ix_users_tenant_id")

    # Add materialized status columns
    op.add_column("users", sa.Column("tenant_status", sa.String(length=20), server_default="ACTIVE", nullable=True))
    op.add_column("users", sa.Column("user_status", sa.String(length=20), server_default="ACTIVE", nullable=True))


def downgrade() -> None:
    op.drop_column("users", "user_status")
    op.drop_column("users", "tenant_status")
    op.execute("ALTER INDEX IF EXISTS ix_users_tenant_id RENAME TO ix_users_tenant_id_cached")
    op.alter_column("users", "tenant_id", new_column_name="tenant_id_cached")
