"""reset self-registered users to the USER role only

Self-registered users (creation_type default/google) may only hold USER
(AI4IDS-3412). RoleService.assign_role enforces that for new grants, but
accounts that were given other roles before the lock still hold them — and
the UI now disables their role control, so an admin can't take those roles
away. This one-time cleanup drops every non-USER role from them and makes
sure each live one holds USER. Confirmed with product before release.

Runs after e7a1b2c3d4f5 (via b8a1957cd6a3), which re-labels admin-created
users still stored as 'default' to 'tenant' — so only genuinely
self-registered accounts are hit.

Excluded / guarded:
  - the seeded guest account (username 'guest', matched the same way as
    e2f3a4b5c6d7) keeps GUEST — it is a system account, not a signup.
  - last admin: if no active admin-created ADMIN would remain, ADMIN is kept
    on the oldest active self-registered ADMIN so the platform is never left
    without one. A warning is logged; promote a real admin, then demote.

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

logger = logging.getLogger("alembic.runtime.migration")

# Self-registered = a known signup type, minus the seeded guest. Scoped to
# the signup labels rather than "not tenant" so an unlabelled (NULL) row is
# never swept — this migration deletes grants, so it must fail open. The
# explicit IS NOT NULL keeps the predicate two-valued: a bare IN (...) is
# NULL for a NULL row, and NOT (NULL) would drop that row from the
# remaining-admin count below.
_SELF_REGISTERED = (
    "u.creation_type IS NOT NULL"
    " AND u.creation_type IN ('default', 'google')"
    " AND u.username <> :guest"
)


def upgrade() -> None:
    conn = op.get_bind()
    params = {"guest": GUEST_USERNAME}

    user_role_id = conn.execute(sa.text("SELECT id FROM roles WHERE name = 'USER'")).scalar()
    if user_role_id is None:
        logger.warning("a7c3e9f15b28: no 'USER' role found; self-registered role reset skipped.")
        return

    # Mirrors RoleRepository.count_admins_in_tenant: active, non-deleted holders.
    admin_created_admins = conn.execute(sa.text(f"""
        SELECT count(DISTINCT u.id)
        FROM users u
        JOIN user_role ur ON ur.user_id = u.id
        JOIN roles r ON r.id = ur.role_id
        WHERE r.name = 'ADMIN'
          AND u.is_active IS TRUE AND u.is_delete IS NOT TRUE
          AND NOT ({_SELF_REGISTERED})
    """), params).scalar()

    keep_admin_user_id = None
    if admin_created_admins == 0:
        keep_admin_user_id = conn.execute(sa.text(f"""
            SELECT u.id
            FROM users u
            JOIN user_role ur ON ur.user_id = u.id
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name = 'ADMIN'
              AND u.is_active IS TRUE AND u.is_delete IS NOT TRUE
              AND {_SELF_REGISTERED}
            ORDER BY u.created_at, u.id
            LIMIT 1
        """), params).scalar()
        if keep_admin_user_id is not None:
            logger.warning(
                "a7c3e9f15b28: user %s is the only active ADMIN and is self-registered; "
                "keeping ADMIN on it. Promote an admin-created user, then remove it.",
                keep_admin_user_id,
            )

    removed = conn.execute(sa.text(f"""
        DELETE FROM user_role ur
        USING users u, roles r
        WHERE ur.user_id = u.id
          AND r.id = ur.role_id
          AND {_SELF_REGISTERED}
          AND r.name <> 'USER'
          AND NOT (r.name = 'ADMIN' AND u.id IS NOT DISTINCT FROM CAST(:keep AS uuid))
        RETURNING ur.user_id, r.name
    """), {**params, "keep": keep_admin_user_id}).fetchall()
    for user_id, role_name in removed:
        logger.info("a7c3e9f15b28: removed role %r from self-registered user %s", role_name, user_id)

    added = conn.execute(sa.text(f"""
        INSERT INTO user_role (user_id, role_id, created_by)
        SELECT u.id, :role_id, CAST(:seeder AS uuid)
        FROM users u
        WHERE {_SELF_REGISTERED}
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
