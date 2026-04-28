"""add_resource_action_to_permissions

Revision ID: 7f4b8e2c9a1d
Revises: b73fa8d05c10
Create Date: 2026-04-28

Adds `resource` and `action` columns to `permissions` and backfills from `name`.
`name` is an enum in Postgres (`permission_name_enum`), so we cast to text for parsing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f4b8e2c9a1d"
down_revision: Union[str, None] = "b73fa8d05c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("permissions", sa.Column("resource", sa.String(length=100), nullable=True))
    op.add_column("permissions", sa.Column("action", sa.String(length=50), nullable=True))

    # Backfill:
    # - action = last segment after the final dot
    # - resource = everything before the final dot (supports multi-dot resources like "tenant.users")
    op.execute(
        sa.text(
            """
            UPDATE permissions
            SET
              action   = regexp_replace(name::text, '^.*\\.', ''),
              resource = regexp_replace(name::text, '\\.[^.]+$', '')
            WHERE resource IS NULL OR action IS NULL
            """
        )
    )

    op.alter_column("permissions", "resource", existing_type=sa.String(length=100), nullable=False)
    op.alter_column("permissions", "action", existing_type=sa.String(length=50), nullable=False)

    op.create_index(op.f("ix_permissions_resource"), "permissions", ["resource"], unique=False)
    op.create_index(op.f("ix_permissions_action"), "permissions", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_permissions_action"), table_name="permissions")
    op.drop_index(op.f("ix_permissions_resource"), table_name="permissions")
    op.drop_column("permissions", "action")
    op.drop_column("permissions", "resource")

