"""backfill creation_type='tenant' for admin-created users stored as default

RoleService.assign_role now treats any creation_type other than 'tenant' as
self-registered and refuses every role but USER (AI4IDS-3412). Between
2026-04-29 and 2026-05-22 CreationType had no TENANT member, so
provision_user stored every admin-created user (institution admins, tenant
users) as 'default'. The seeded platform admin is also inserted as 'default'.
Without this backfill those accounts could no longer be given other roles.

A 'default' user is admin-created when:
  - it has no user_credentials row: self-registration creates credentials in
    the same transaction as the user, so only a provisioned account that
    never consumed its setup link has none (Google signups are 'google' and
    are not touched); or
  - its credentials were created after the user: registration inserts both
    rows in one transaction so their now()-based created_at match exactly,
    while a provisioned user's credentials are created later by
    set_password_with_token. Password reset/change update the row in place
    and never move its created_at; or
  - it is the seeded platform admin (created_by = SEEDER_ID with the ADMIN
    role). The seeded guest stays 'default' on purpose — its password is a
    shared env value, so it must not become promotable.

Revision ID: e7a1b2c3d4f5
Revises: 74435be97765
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e7a1b2c3d4f5"
down_revision: Union[str, None] = "74435be97765"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"


def upgrade() -> None:
    op.get_bind().execute(sa.text(f"""
        UPDATE users u
        SET creation_type = 'tenant'
        WHERE (u.creation_type = 'default' OR u.creation_type IS NULL)
          AND (
              NOT EXISTS (
                  SELECT 1 FROM user_credentials c WHERE c.user_id = u.id
              )
              OR EXISTS (
                  SELECT 1 FROM user_credentials c
                  WHERE c.user_id = u.id AND c.created_at <> u.created_at
              )
              OR (
                  u.created_by = '{SEEDER_ID}'
                  AND EXISTS (
                      SELECT 1 FROM user_role ur
                      JOIN roles r ON r.id = ur.role_id
                      WHERE ur.user_id = u.id AND r.name = 'ADMIN'
                  )
              )
          )
    """))


def downgrade() -> None:
    # No-op: the rows this moved can't be told apart from users that were
    # created as 'tenant' to begin with, so reverting would mislabel those.
    pass
