"""Fix guest user role assignment.

Some environments ended up with the guest account (username 'guest', seeded
by 2362774ac241_seed_default_data) holding the USER role instead of GUEST -
e.g. the account existed with a different role before the GUEST-role seed
step ran, so its NOT-EXISTS-guarded insert into user_role became a no-op and
never corrected it.

The account is matched by username rather than email: users.email is an
EncryptedEmail column, and any row touched by the app (as opposed to a raw
seed INSERT) stores AES-SIV ciphertext, not plaintext - matching on email
would silently miss exactly the app-touched accounts this migration exists
to fix. username is a plain, uniquely-indexed column and is never encrypted.

This migration fixes the assignment directly: it drops any non-GUEST role
on the guest account and ensures GUEST is assigned, regardless of the
account's current state. Safe to run repeatedly and in any environment.

Revision ID: e2f3a4b5c6d7
Revises: d6e7f8a9b1c2
Create Date: 2026-08-26 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd6e7f8a9b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
GUEST_USERNAME = "guest"

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()

    guest_user = conn.execute(
        sa.text("SELECT id FROM users WHERE username = :username"),
        {"username": GUEST_USERNAME},
    ).fetchone()
    if not guest_user:
        logger.warning(
            "e2f3a4b5c6d7: no user found with username=%r; guest role fix skipped.",
            GUEST_USERNAME,
        )
        return
    guest_user_id = guest_user[0]

    guest_role = conn.execute(
        sa.text("SELECT id FROM roles WHERE name = 'GUEST'")
    ).fetchone()
    if not guest_role:
        logger.warning(
            "e2f3a4b5c6d7: no 'GUEST' role found in roles table; guest role fix skipped."
        )
        return
    guest_role_id = guest_role[0]

    # Drop any role assignment on the guest account other than GUEST.
    conn.execute(
        sa.text("""
            DELETE FROM user_role
            WHERE user_id = :user_id AND role_id != :role_id
        """),
        {"user_id": guest_user_id, "role_id": guest_role_id},
    )

    conn.execute(
        sa.text("""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT :user_id, :role_id, :created_by
            WHERE NOT EXISTS (
                SELECT 1 FROM user_role WHERE user_id = :user_id AND role_id = :role_id
            )
        """),
        {"user_id": guest_user_id, "role_id": guest_role_id, "created_by": SEEDER_ID},
    )


def downgrade() -> None:
    # Data-correction migration; the prior (incorrect) role assignment isn't
    # recoverable, so downgrade is a no-op.
    pass
