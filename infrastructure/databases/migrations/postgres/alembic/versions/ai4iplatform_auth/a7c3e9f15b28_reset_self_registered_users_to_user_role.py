"""reset self-registered users to the USER role only

Self-registered users (creation_type default/google) may only hold USER
(AI4IDS-3412). RoleService.assign_role enforces that for new grants. This
one-time cleanup brings existing self-registered accounts in line: their
roles other than USER are removed and each live one is given USER.

Change request: self-registered users who already hold a privileged role
(ADMIN, MODERATOR, TENANT ADMIN or USAGE VIEWER) keep their roles. Such a
user is left exactly as it is — nothing removed, nothing added — so no
working admin, moderator or usage viewer loses access. Only the other
self-registered users are reset.

Runs after e7a1b2c3d4f5 (via b8a1957cd6a3), which re-labels admin-created
users still stored as 'default' to 'tenant' — so only genuinely
self-registered accounts are considered.

Excluded:
  - the seeded guest account (username 'guest', matched the same way as
    e2f3a4b5c6d7) keeps GUEST — it is a system account, not a signup.

Affected user ids and the roles removed are logged (ids only, no PII).
Existing access tokens keep their old permission_ids until they expire;
the next refresh re-reads roles from the DB.

Revision ID: a7c3e9f15b28
Revises: b8a1957cd6a3
Create Date: 2026-10-27

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7c3e9f15b28"
down_revision: Union[str, None] = "b8a1957cd6a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

SEEDER_ID = "5eed0000-0000-0000-0000-000000000000"
GUEST_USERNAME = "guest"

# A self-registered user holding any of these keeps all of its roles.
PRESERVED_ROLES = ("ADMIN", "MODERATOR", "TENANT ADMIN", "USAGE VIEWER")

logger = logging.getLogger("alembic.runtime.migration")

# Self-registered = a known signup type, minus the seeded guest. Scoped to
# the signup labels rather than "not tenant" so an unlabelled (NULL) row is
# never swept — this migration deletes grants, so it must fail open.
_SELF_REGISTERED = (
    "u.creation_type IS NOT NULL"
    " AND u.creation_type IN ('default', 'google')"
    " AND u.username <> :guest"
)

# Users holding a preserved role are left untouched.
_NO_PRESERVED_ROLE = """
    NOT EXISTS (
        SELECT 1 FROM user_role kept
        JOIN roles kr ON kr.id = kept.role_id
        WHERE kept.user_id = u.id AND kr.name IN :preserved
    )
"""


def _params() -> dict:
    return {"guest": GUEST_USERNAME, "preserved": PRESERVED_ROLES}


def upgrade() -> None:
    conn = op.get_bind()

    user_role_id = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'USER'")).scalar()
    if user_role_id is None:
        logger.warning("a7c3e9f15b28: no 'USER' role found; self-registered role reset skipped.")
        return

    removed = conn.execute(
        sa.text(f"""
            DELETE FROM user_role ur
            USING users u, roles r
            WHERE ur.user_id = u.id
              AND r.id = ur.role_id
              AND {_SELF_REGISTERED}
              AND {_NO_PRESERVED_ROLE}
              AND r.name <> 'USER'
            RETURNING ur.user_id, r.name
        """).bindparams(sa.bindparam("preserved", expanding=True)),
        _params(),
    ).fetchall()
    for user_id, role_name in removed:
        logger.info("a7c3e9f15b28: removed role %r from self-registered user %s", role_name, user_id)

    added = conn.execute(
        sa.text(f"""
            INSERT INTO user_role (user_id, role_id, created_by)
            SELECT u.id, :role_id, CAST(:seeder AS uuid)
            FROM users u
            WHERE {_SELF_REGISTERED}
              AND {_NO_PRESERVED_ROLE}
              AND u.is_delete IS NOT TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM user_role ur
                  WHERE ur.user_id = u.id AND ur.role_id = :role_id
              )
            RETURNING user_id
        """).bindparams(sa.bindparam("preserved", expanding=True)),
        {**_params(), "role_id": user_role_id, "seeder": SEEDER_ID},
    ).fetchall()
    for (user_id,) in added:
        logger.info("a7c3e9f15b28: assigned USER to self-registered user %s", user_id)

    logger.info(
        "a7c3e9f15b28: removed %d role assignment(s), added USER to %d user(s); "
        "self-registered users holding %s were left unchanged.",
        len(removed), len(added), ", ".join(PRESERVED_ROLES),
    )


def downgrade() -> None:
    # No-op: the removed grants were never meant to exist; the upgrade log
    # lists them if one has to be restored by hand.
    pass
