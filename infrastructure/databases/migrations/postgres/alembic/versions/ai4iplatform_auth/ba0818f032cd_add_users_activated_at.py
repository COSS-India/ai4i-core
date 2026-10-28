"""add users.activated_at

The tenant-user list derived "activated" from a user_credentials row, so a
self-registered user waiting on email verification (password stored at
signup, is_active false) showed as Suspended instead of Pending Activation,
and a suspended Google user (no credentials) showed as Pending Activation.
activated_at records the first time an account became active and is never
cleared.

Backfill marks a user activated when:
  - it is active now; or
  - it has logged in (only an active account can); or
  - it is not self-registered and has credentials: a provisioned user only
    gets credentials from set_password_with_token, which activates it.
Runs after e7a1b2c3d4f5, which re-labels admin-created users to 'tenant'.
A self-registered user with credentials who verified, never logged in and
was then suspended is indistinguishable from an unverified one and stays
Pending Activation.

Revision ID: ba0818f032cd
Revises: 7a28dca07e9d
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ba0818f032cd"
down_revision: Union[str, None] = "7a28dca07e9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE users u
        SET activated_at = COALESCE(u.last_login, u.created_at, now())
        WHERE u.is_active
           OR u.last_login IS NOT NULL
           OR (
                (u.creation_type IS NULL OR u.creation_type NOT IN ('default', 'google'))
                AND EXISTS (SELECT 1 FROM user_credentials c WHERE c.user_id = u.id)
           )
        """
    )


def downgrade() -> None:
    op.drop_column("users", "activated_at")
