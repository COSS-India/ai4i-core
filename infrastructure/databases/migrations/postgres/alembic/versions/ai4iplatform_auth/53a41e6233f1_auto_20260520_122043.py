"""Extend creation_type_enum with tenant (native PostgreSQL ENUM)

Revision ID: 53a41e6233f1
Revises: aca4be0874b3
Create Date: 2026-05-20 06:50:45.606257

Keeps users.creation_type as native PostgreSQL ENUM (matches auth-service model).
Adds label ``tenant``. If a prior revision stored the column as VARCHAR, converts
it back to creation_type_enum.

Does not change tenants.status — that is c4e8f1a2b3d0 (+ no-op aca4be0874b3 / 5f775ba90435).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "53a41e6233f1"
down_revision: Union[str, None] = "aca4be0874b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATION_TYPE_LABELS = ("default", "google", "tenant")


def _column_udt_name(connection) -> str | None:
    return connection.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'users'
              AND column_name = 'creation_type'
            """
        )
    ).scalar()


def upgrade() -> None:
    connection = op.get_bind()
    udt_name = _column_udt_name(connection)

    if udt_name == "varchar":
        op.execute(
            """
            DO $migration$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'creation_type_enum') THEN
                    CREATE TYPE creation_type_enum AS ENUM ('default', 'google', 'tenant');
                END IF;
            END $migration$;
            """
        )
        op.alter_column(
            "users",
            "creation_type",
            existing_type=sa.String(length=32),
            type_=postgresql.ENUM(
                *_CREATION_TYPE_LABELS, name="creation_type_enum", create_type=False
            ),
            postgresql_using="creation_type::creation_type_enum",
            existing_nullable=True,
            existing_server_default=sa.text("'default'"),
        )
        op.alter_column(
            "users",
            "creation_type",
            existing_type=postgresql.ENUM(
                *_CREATION_TYPE_LABELS, name="creation_type_enum", create_type=False
            ),
            server_default=sa.text("'default'::creation_type_enum"),
            existing_nullable=True,
        )
        return

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
    connection = op.get_bind()
    udt_name = _column_udt_name(connection)

    op.execute(
        """
        UPDATE users
        SET creation_type = 'default'
        WHERE creation_type::text = 'tenant'
        """
    )

    if udt_name == "varchar":
        return

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
