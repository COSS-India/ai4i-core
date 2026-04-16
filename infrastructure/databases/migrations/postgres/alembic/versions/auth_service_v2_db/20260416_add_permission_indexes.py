"""Add indexes on permissions.resource and permissions.action.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_permissions_resource", "permissions", ["resource"], unique=False)
    op.create_index("ix_permissions_action", "permissions", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_permissions_action", table_name="permissions")
    op.drop_index("ix_permissions_resource", table_name="permissions")
