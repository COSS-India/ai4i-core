"""Backfill tenant_id on OAuth-registered users

OAuth-registered users (currently only Google sign-in, ``creation_type='google'``)
were created without a ``tenant_id`` because ``OAuthService._get_or_create_user``
didn't call ``resolve_tenant_id`` like the email/password path. That code path
is now fixed; this migration backfills the existing rows so they show up on the
Role Assignment page like direct-signup users.

Resolution rule:
  * Read the default-tenant org name from the ``DEFAULT_TENANT_ORG`` env var
    (same lookup the seed migration uses) — falls back to ``"default organisation"``.
  * Match the row in ``tenants`` by ``organisation`` and assign its ``id``.
  * If the default tenant doesn't exist, log a warning and skip — no destructive
    change. Operators should re-run after seeding the default tenant.

Downgrade restores ``tenant_id`` to ``NULL`` for the same set of rows (OAuth
users whose tenant_id is the default tenant), so the migration is reversible
in environments where the bug never had data committed against it.

Revision ID: e7c9a4b2d1f3
Revises: d7a1c3f9e2b4
Create Date: 2026-06-01 08:30:00.000000

"""
import logging
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c9a4b2d1f3'
down_revision: Union[str, None] = 'd7a1c3f9e2b4'
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, None] = None


logger = logging.getLogger("alembic.runtime.migration")


def _default_tenant_id(conn) -> int | None:
    """Look up the default tenant by organisation name; mirrors the seed migration."""
    org = (os.getenv("DEFAULT_TENANT_ORG") or "default organisation").strip()
    row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE organisation = :org LIMIT 1"),
        {"org": org},
    ).fetchone()
    if row is None:
        logger.warning(
            "Default tenant '%s' not found; OAuth-user backfill skipped. "
            "Re-run this migration after seeding the default tenant.",
            org,
        )
        return None
    return int(row[0])


def upgrade() -> None:
    conn = op.get_bind()
    tenant_id = _default_tenant_id(conn)
    if tenant_id is None:
        return

    result = conn.execute(
        sa.text(
            """
            UPDATE users
            SET tenant_id = :tenant_id
            WHERE tenant_id IS NULL
              AND creation_type = 'google'
            """
        ),
        {"tenant_id": tenant_id},
    )
    logger.info(
        "Backfilled tenant_id=%s on %d OAuth users (creation_type='google').",
        tenant_id, result.rowcount,
    )


def downgrade() -> None:
    conn = op.get_bind()
    tenant_id = _default_tenant_id(conn)
    if tenant_id is None:
        return

    result = conn.execute(
        sa.text(
            """
            UPDATE users
            SET tenant_id = NULL
            WHERE tenant_id = :tenant_id
              AND creation_type = 'google'
            """
        ),
        {"tenant_id": tenant_id},
    )
    logger.info(
        "Reverted tenant_id to NULL on %d OAuth users.",
        result.rowcount,
    )
