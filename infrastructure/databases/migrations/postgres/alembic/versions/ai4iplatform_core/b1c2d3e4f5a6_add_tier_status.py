"""add_tier_status

Add a native Postgres enum (tier_status_enum) and a status column to the
tiers table. Backfills existing rows: is_active=true → ACTIVE,
is_active=false → INACTIVE. The is_active boolean is kept in this migration
— it is dropped in a later migration once every reader in both services is
on status.

Revision ID: b1c2d3e4f5a6
Revises: 6144f82e9ad3
Create Date: 2026-09-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "6144f82e9ad3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ENUM_NAME = "tier_status_enum"
_ENUM_VALUES = ("INACTIVE", "ACTIVE", "DEACTIVATED", "DELETED")


def upgrade() -> None:
    conn = op.get_bind()

    tier_status = sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME)
    tier_status.create(conn, checkfirst=True)

    op.add_column(
        "tiers",
        sa.Column(
            "status",
            sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME, create_type=False),
            nullable=True,
        ),
    )

    # Backfill: is_active=true → ACTIVE, is_active=false → INACTIVE
    op.execute(
        f"""
        UPDATE tiers
        SET status = CASE
            WHEN is_active = true THEN 'ACTIVE'::{_ENUM_NAME}
            ELSE 'INACTIVE'::{_ENUM_NAME}
        END
        """
    )

    op.alter_column("tiers", "status", nullable=False)


def downgrade() -> None:
    op.drop_column("tiers", "status")
    sa.Enum(name=_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
