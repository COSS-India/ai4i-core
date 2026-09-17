"""backfill budget-exhausted for keys with no allocated_budget

APIKeyService.create_api_key now treats allocated_budget IS NULL as
exhausted unconditionally (previously only blocked when the owning Tenant
ALSO had no Budget - a Key under an Application deliberately left with no
budget of its own, even under a funded Tenant, was "intentionally
uncapped" and never flagged). That fix only changes what NEW
create_api_key calls do; a Key created before it shipped already has its
cached_data written WITHOUT budget-exhausted, and nothing else ever
re-visits it - the allocation engine only recomputes this flag for a Key
that actually participates in a Budget Allocation edit. A Key whose
Application was never touched by one stays exactly as it was created,
serving every request indefinitely with no budget_usage row and no
enforcement.

This patches api_key.cached_data (the DB-backed write-through snapshot
every Redis-miss rehydrate serves verbatim - see
APIKeyService._rehydrate_cache_from_db) for every active key with
allocated_budget IS NULL, merging "budget-exhausted": "1" into whatever
is already there rather than overwriting it. Deliberately DB-only: an
already-cached Redis hash for one of these keys keeps serving its current
(unflagged) state until it naturally expires or is next refreshed by any
of the normal write paths (a rename, a tier change, a Budget Allocation
edit) - the same bounded, self-healing lag every other cache-only field
in this table already has. Safe to run repeatedly.

Revision ID: f3a9b1c7d2e6
Revises: 569df8229653
Create Date: 2026-09-17 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a9b1c7d2e6'
down_revision: Union[str, None] = '569df8229653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            UPDATE api_key
            SET cached_data = COALESCE(cached_data, '{}'::jsonb)
                || '{"budget-exhausted": "1"}'::jsonb
            WHERE allocated_budget IS NULL
              AND is_active = true
            """
        )
    )
    logger.info(
        "f3a9b1c7d2e6: backfilled budget-exhausted for %d active key(s) with no "
        "allocated_budget.",
        result.rowcount,
    )


def downgrade() -> None:
    # Data-correction migration; which rows were touched (vs. already having
    # budget-exhausted=1 from some other, legitimate reason) isn't
    # recoverable, so downgrade is a no-op.
    pass
