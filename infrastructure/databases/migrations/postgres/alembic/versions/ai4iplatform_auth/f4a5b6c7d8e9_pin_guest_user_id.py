"""pin_guest_user_id

Revision ID: f4a5b6c7d8e9
Revises: a2b3c4d5e6f7
Create Date: 2026-08-07 00:00:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

# Fixed id the guest user must have on every environment, regardless of when
# it was originally seeded (the seed migration assigns a random uuid4()).
GUEST_USER_ID = "3308a584-8ebf-4ffd-9b98-6031e82fbe60"


def upgrade() -> None:
    conn = op.get_bind()

    guest_email = (os.getenv("GUEST_EMAIL") or "guest@ai4inclusion.org").strip()

    guest_row = conn.execute(
        sa.text("SELECT id, email, username FROM users WHERE email = :email"),
        {"email": guest_email},
    ).fetchone()

    if guest_row is None:
        return

    old_id, email, username = str(guest_row[0]), guest_row[1], guest_row[2]

    if old_id == GUEST_USER_ID:
        return

    # Email/username are unique, so the new row is created with temporary
    # placeholders until the old row is removed, then renamed back.
    conn.execute(
        sa.text("""
            INSERT INTO users (
                id, email, username, full_name, is_active, tenant_id,
                last_login, avatar_url, phone_number, timezone, is_delete,
                is_tenant_active, creation_type, created_at, created_by,
                updated_at, updated_by
            )
            SELECT
                :new_id, email || '.pin-tmp', username || '_pin_tmp', full_name,
                is_active, tenant_id, last_login, avatar_url, phone_number,
                timezone, is_delete, is_tenant_active, creation_type,
                created_at, created_by, updated_at, updated_by
            FROM users WHERE id = :old_id
        """),
        {"new_id": GUEST_USER_ID, "old_id": old_id},
    )

    for table in ("api_key", "refresh", "user_credentials", "user_role"):
        conn.execute(
            sa.text(f"UPDATE {table} SET user_id = :new_id WHERE user_id = :old_id"),
            {"new_id": GUEST_USER_ID, "old_id": old_id},
        )

    conn.execute(sa.text("DELETE FROM users WHERE id = :old_id"), {"old_id": old_id})

    conn.execute(
        sa.text("UPDATE users SET email = :email, username = :username WHERE id = :new_id"),
        {"email": email, "username": username, "new_id": GUEST_USER_ID},
    )


def downgrade() -> None:
    # The guest user's original id was a random uuid4() discarded by
    # upgrade(); there is nothing meaningful to restore it to.
    pass
