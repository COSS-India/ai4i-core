"""encrypt user/tenant email & phone at rest (schema only)

Prepares the schema for transparent, application-level PII encryption:

  * widens the email/phone columns to TEXT, since the deterministic AES-SIV
    ciphertext the app now writes is longer than the original plaintext, and
  * replaces the tenants ``lower(email)`` expression index with a plain unique
    index on ``email`` — the app lower-normalises before encrypting, so a plain
    unique index on the deterministic ciphertext already enforces
    case-insensitive uniqueness.

This migration deliberately does NOT touch existing row data. Encryption is
handled entirely by the application's SQLAlchemy column types on read/write, and
any pre-existing data is reset as part of rolling out this change. As a result
the migration has no dependency on ``pii_crypto`` and the Alembic environment
does NOT need ``PII_ENCRYPTION_KEY`` configured.

Revision ID: b7e1c9a4f2d0
Revises: 1c2d3e4f5a6b
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e1c9a4f2d0"
down_revision: Union[str, None] = "1c2d3e4f5a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # 1. Widen columns so the encrypted ciphertext (longer than plaintext) fits.
    op.alter_column("users", "email", type_=sa.Text(), existing_nullable=False)
    op.alter_column("users", "phone_number", type_=sa.Text(), existing_nullable=True)
    op.alter_column("tenants", "email", type_=sa.Text(), existing_nullable=False)
    op.alter_column("tenants", "phone_number", type_=sa.Text(), existing_nullable=True)

    # 2. Replace tenants' lower(email) expression index with a plain unique index.
    #    The app lower-normalises email before encrypting, so a plain unique index
    #    on the deterministic ciphertext enforces case-insensitive uniqueness.
    op.execute("DROP INDEX IF EXISTS uq_tenants_email_lower")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_email ON tenants (email)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_email")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_email_lower "
        "ON tenants (lower(email))"
    )

    op.alter_column(
        "users", "email", type_=sa.String(length=255), existing_nullable=False
    )
    op.alter_column(
        "users", "phone_number", type_=sa.String(length=20), existing_nullable=True
    )
    op.alter_column(
        "tenants", "email", type_=sa.String(length=255), existing_nullable=False
    )
    op.alter_column(
        "tenants", "phone_number", type_=sa.String(length=20), existing_nullable=True
    )
