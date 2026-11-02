"""drop api_key_revoked_at from api_key

Revision ID: b8a1957cd6a3
Revises: e7a1b2c3d4f5
Create Date: 2026-10-26

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migration_registry import get_redis_client

revision: str = "b8a1957cd6a3"
down_revision: Union[str, None] = "e7a1b2c3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    # A key whose current value was revoked on its own is revoked as a whole;
    # its values' Redis entries go too, or they keep authenticating until TTL.
    rows = op.get_bind().execute(sa.text(
        "UPDATE api_key SET is_active = false "
        "WHERE api_key_revoked_at IS NOT NULL AND is_active "
        "RETURNING api_key, rotated_key"
    )).fetchall()
    op.drop_column("api_key", "api_key_revoked_at")

    values = [value for row in rows for value in row if value]
    if not values:
        return
    client = get_redis_client()
    if client is None:
        logger.warning("b8a1957cd6a3: Redis unreachable; %d revoked key value(s) stay cached until TTL", len(values))
        return
    try:
        client.delete(*(f"auth:apikey:{value}" for value in values))
    except Exception as exc:  # noqa: BLE001 - the DB revoke above must not roll back over Redis
        logger.warning("b8a1957cd6a3: could not delete Redis entries (%s); they stop at TTL", exc)
    finally:
        client.close()


def downgrade() -> None:
    """Re-adds the column empty. Keys the upgrade revoked stay revoked and
    can't be told apart from other revoked keys; restore them from the
    pre-migration backup."""
    op.add_column("api_key", sa.Column("api_key_revoked_at", sa.DateTime(timezone=True), nullable=True))
