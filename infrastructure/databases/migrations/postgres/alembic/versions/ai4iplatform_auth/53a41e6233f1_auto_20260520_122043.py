"""Add tenant label to creation_type_enum

Revision ID: 53a41e6233f1
Revises: c4e8f1a2b3d0
Create Date: 2026-05-20 06:50:45.606257

Adds the tenant label only. Does not change tenants.status (see c4e8f1a2b3d0).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "53a41e6233f1"
down_revision: Union[str, None] = "c4e8f1a2b3d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $migration$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'creation_type_enum'
                  AND e.enumlabel = 'tenant'
            ) THEN
                ALTER TYPE creation_type_enum ADD VALUE 'tenant';
            END IF;
        END $migration$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET creation_type = 'default'
        WHERE creation_type::text = 'tenant'
        """
    )
    op.execute(
        """
        DO $migration$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'creation_type_enum') THEN
                ALTER TYPE creation_type_enum RENAME TO creation_type_enum_old;
            END IF;
            CREATE TYPE creation_type_enum AS ENUM ('default', 'google');
            ALTER TABLE users ALTER COLUMN creation_type DROP DEFAULT;
            ALTER TABLE users
                ALTER COLUMN creation_type TYPE creation_type_enum
                USING creation_type::text::creation_type_enum;
            DROP TYPE IF EXISTS creation_type_enum_old;
            ALTER TABLE users
                ALTER COLUMN creation_type SET DEFAULT 'default'::creation_type_enum;
        END $migration$;
        """
    )
