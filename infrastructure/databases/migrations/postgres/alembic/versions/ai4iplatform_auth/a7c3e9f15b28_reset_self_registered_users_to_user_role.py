"""reset non-privileged self-registered users to USER

A self-registered user (creation_type default/google) holding ADMIN,
MODERATOR, TENANT ADMIN or USAGE VIEWER keeps all its roles. The rest,
except the seeded guest, are left with USER only.

Runs after e7a1b2c3d4f5, which re-labels admin-created users to 'tenant',
and c5d6e7f8a9b1, which renames PROGRAM ADMIN to USAGE VIEWER.

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

logger = logging.getLogger("alembic.runtime.migration")

# Self-registered users holding any of these keep every role they have.
PRESERVED_ROLES = ("ADMIN", "MODERATOR", "TENANT ADMIN", "USAGE VIEWER")

# Self-registered = a known signup type, minus the seeded guest. Scoped to
# the signup labels rather than "not tenant" so an unlabelled (NULL) row is
# never swept — this migration deletes grants, so it must fail open.
_SELF_REGISTERED = (
    "u.creation_type IS NOT NULL"
    " AND u.creation_type IN ('default', 'google')"
    " AND u.username <> :guest"
)

# The users this migration touches. The DELETE below never removes a
# preserved role, so the predicate gives the same set for the INSERT.
_TO_RESET = _SELF_REGISTERED + """
    AND NOT EXISTS (
        SELECT 1 FROM user_role pur
        JOIN roles pr ON pr.id = pur.role_id
        WHERE pur.user_id = u.id
          AND pr.name IN ({})
    )""".format(", ".join(f"'{name}'" for name in PRESERVED_ROLES))


def upgrade() -> None:
    conn = op.get_bind()
    params = {"guest": GUEST_USERNAME}

    user_role_id = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'USER'")).scalar()
    if user_role_id is None:
        logger.warning("a7c3e9f15b28: no 'USER' role found; non-privileged self-registered role reset skipped.")
        return

    removed = conn.execute(sa.text(f"""
        DELETE FROM user_role ur
        USING users u, roles r
        WHERE ur.user_id = u.id
          AND r.id = ur.role_id
          AND {_TO_RESET}
          AND r.name <> 'USER'
        RETURNING ur.user_id, r.name
    """), params).fetchall()
    for user_id, role_name in removed:
        logger.info("a7c3e9f15b28: removed role %r from self-registered user %s", role_name, user_id)

    added = conn.execute(sa.text(f"""
        INSERT INTO user_role (user_id, role_id, created_by)
        SELECT u.id, :role_id, CAST(:seeder AS uuid)
        FROM users u
        WHERE {_TO_RESET}
          AND u.is_delete IS NOT TRUE
          AND NOT EXISTS (
              SELECT 1 FROM user_role ur
              WHERE ur.user_id = u.id AND ur.role_id = :role_id
          )
        RETURNING user_id
    """), {**params, "role_id": user_role_id, "seeder": SEEDER_ID}).fetchall()
    for (user_id,) in added:
        logger.info("a7c3e9f15b28: assigned USER to self-registered user %s", user_id)

    logger.info(
        "a7c3e9f15b28: removed %d role assignment(s), added USER to %d user(s).",
        len(removed), len(added),
    )


def downgrade() -> None:
    # No-op: the removed grants were never meant to exist; the upgrade log
    # lists them if one has to be restored by hand.
    pass
