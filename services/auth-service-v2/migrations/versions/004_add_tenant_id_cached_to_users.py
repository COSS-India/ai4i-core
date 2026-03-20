"""Add tenant_id_cached to users table.

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tenant_id_cached", sa.String(100), nullable=True))
    op.create_index("ix_users_tenant_id_cached", "users", ["tenant_id_cached"])


def downgrade() -> None:
    op.drop_index("ix_users_tenant_id_cached", table_name="users")
    op.drop_column("users", "tenant_id_cached")
