"""nmt_requests: drop cross-service FK constraints, user/api_key/session_id INTEGER → VARCHAR(64)

Revision ID: cc1a5d8e3f9b
Revises: a55cc68a99ce
Create Date: 2026-05-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cc1a5d8e3f9b'
down_revision: Union[str, None] = 'a55cc68a99ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Guard: if nmt_requests doesn't exist yet, create_all() will use the already-fixed
    # ORM model (String(64), no FKs) — nothing to do here.
    table_exists = conn.execute(
        sa.text("SELECT to_regclass('public.nmt_requests') IS NOT NULL")
    ).scalar()
    if not table_exists:
        return

    # Drop FK constraints if they still exist (idempotent for environments
    # where the manual ALTER was already applied).
    op.execute("ALTER TABLE nmt_requests DROP CONSTRAINT IF EXISTS nmt_requests_user_id_fkey")
    op.execute("ALTER TABLE nmt_requests DROP CONSTRAINT IF EXISTS nmt_requests_api_key_id_fkey")
    op.execute("ALTER TABLE nmt_requests DROP CONSTRAINT IF EXISTS nmt_requests_session_id_fkey")

    # Alter column types INTEGER → VARCHAR(64). USING clause required for int→text cast.
    # These are no-ops if columns are already VARCHAR(64) (e.g. post-manual-fix envs).
    op.execute(
        "ALTER TABLE nmt_requests "
        "ALTER COLUMN user_id TYPE VARCHAR(64) USING user_id::text, "
        "ALTER COLUMN api_key_id TYPE VARCHAR(64) USING api_key_id::text, "
        "ALTER COLUMN session_id TYPE VARCHAR(64) USING session_id::text"
    )


def downgrade() -> None:
    # Reversing VARCHAR(64) → INTEGER will fail if any UUID values are present.
    # This is intentional: once UUIDs are stored, a safe downgrade requires a data migration.
    op.execute(
        "ALTER TABLE nmt_requests "
        "ALTER COLUMN session_id TYPE INTEGER USING session_id::integer, "
        "ALTER COLUMN api_key_id TYPE INTEGER USING api_key_id::integer, "
        "ALTER COLUMN user_id TYPE INTEGER USING user_id::integer"
    )
