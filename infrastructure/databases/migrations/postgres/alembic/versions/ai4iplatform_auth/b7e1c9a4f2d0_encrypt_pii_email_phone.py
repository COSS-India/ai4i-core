"""encrypt user/tenant email & phone at rest

Widens the email/phone columns to TEXT, encrypts every existing value with the
deterministic AES-SIV scheme (so duplicate-email detection keeps working via
direct ciphertext comparison), and replaces the tenants lower(email) expression
index with a plain unique index on the encrypted value.

Requires PII_ENCRYPTION_KEY (base64/hex AES-SIV key) in the migration
environment — the SAME key auth-service uses. The crypto helper is imported
from auth-service, which the centralized Alembic env adds to sys.path.

Idempotent: encryption skips values already carrying the ``enc:v1:`` prefix,
so re-running upgrade is safe.

Revision ID: b7e1c9a4f2d0
Revises: 0c5afbf03dee
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# auth-service is placed on sys.path by the centralized Alembic env
# (migration_registry._load_auth_service_metadata), so this import resolves.
from app.core import pii_crypto

# revision identifiers, used by Alembic.
revision: str = "b7e1c9a4f2d0"
down_revision: Union[str, None] = "0c5afbf03dee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def _encrypt_existing(conn) -> None:
    # Users: email (deterministic, lower-normalised) + phone.
    for user_id, email, phone in conn.execute(
        sa.text("SELECT id, email, phone_number FROM users")
    ).fetchall():
        new_email = pii_crypto.encrypt(
            email.strip().lower() if email else email, pii_crypto.EMAIL_CONTEXT
        )
        new_phone = pii_crypto.encrypt(phone, pii_crypto.PHONE_CONTEXT)
        conn.execute(
            sa.text(
                "UPDATE users SET email = :email, phone_number = :phone WHERE id = :id"
            ),
            {"email": new_email, "phone": new_phone, "id": user_id},
        )

    # Tenants: email (deterministic, lower-normalised) + phone.
    for tenant_id, email, phone in conn.execute(
        sa.text("SELECT id, email, phone_number FROM tenants")
    ).fetchall():
        new_email = pii_crypto.encrypt(
            email.strip().lower() if email else email, pii_crypto.EMAIL_CONTEXT
        )
        new_phone = pii_crypto.encrypt(phone, pii_crypto.PHONE_CONTEXT)
        conn.execute(
            sa.text(
                "UPDATE tenants SET email = :email, phone_number = :phone WHERE id = :id"
            ),
            {"email": new_email, "phone": new_phone, "id": tenant_id},
        )


def _decrypt_existing(conn) -> None:
    for user_id, email, phone in conn.execute(
        sa.text("SELECT id, email, phone_number FROM users")
    ).fetchall():
        conn.execute(
            sa.text(
                "UPDATE users SET email = :email, phone_number = :phone WHERE id = :id"
            ),
            {
                "email": pii_crypto.decrypt(email, pii_crypto.EMAIL_CONTEXT),
                "phone": pii_crypto.decrypt(phone, pii_crypto.PHONE_CONTEXT),
                "id": user_id,
            },
        )
    for tenant_id, email, phone in conn.execute(
        sa.text("SELECT id, email, phone_number FROM tenants")
    ).fetchall():
        conn.execute(
            sa.text(
                "UPDATE tenants SET email = :email, phone_number = :phone WHERE id = :id"
            ),
            {
                "email": pii_crypto.decrypt(email, pii_crypto.EMAIL_CONTEXT),
                "phone": pii_crypto.decrypt(phone, pii_crypto.PHONE_CONTEXT),
                "id": tenant_id,
            },
        )


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Widen columns so ciphertext (longer than plaintext) fits.
    op.alter_column("users", "email", type_=sa.Text(), existing_nullable=False)
    op.alter_column("users", "phone_number", type_=sa.Text(), existing_nullable=True)
    op.alter_column("tenants", "email", type_=sa.Text(), existing_nullable=False)
    op.alter_column("tenants", "phone_number", type_=sa.Text(), existing_nullable=True)

    # 2. Encrypt every existing row in place.
    _encrypt_existing(conn)

    # 3. Replace tenants' lower(email) expression index with a plain unique index
    #    on the (now deterministic, lower-normalised) ciphertext.
    op.execute("DROP INDEX IF EXISTS uq_tenants_email_lower")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_email ON tenants (email)")


def downgrade() -> None:
    conn = op.get_bind()

    op.execute("DROP INDEX IF EXISTS uq_tenants_email")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_email_lower ON tenants (lower(email))")

    # Decrypt back to plaintext before narrowing column types.
    _decrypt_existing(conn)

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
