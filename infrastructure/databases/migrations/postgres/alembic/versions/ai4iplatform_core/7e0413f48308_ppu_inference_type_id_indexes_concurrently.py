"""ppu_inference_type_id_indexes_concurrently

Builds the two ``inference_type_id`` FK indexes without blocking writers.

Split out of 11f21f7d7ae4, which created them with a plain ``CREATE INDEX``
alongside a row-locking backfill UPDATE. That combination takes a SHARE lock on
``tier_quotas`` and ``quota_usage`` and holds it, plus the UPDATE's row locks,
until the revision commits. ``payperuse_consumer`` upserts ``quota_usage`` on
every billed span, so it would block for the whole build — and past
``max.poll.interval.ms`` (300s) the consumer is evicted from its group, rebalances
and redelivers.

``CREATE INDEX CONCURRENTLY`` takes only SHARE UPDATE EXCLUSIVE, which permits
concurrent DML. It cannot run inside a transaction block, hence
``autocommit_block()`` — which in turn needs ``transaction_per_migration=True``
in env.py so this revision owns its own transaction to step out of.

Two consequences of CONCURRENTLY worth knowing before you run this:

* It is not atomic. If the build fails (a deadlock, a cancelled session, a
  conflicting long transaction), Postgres leaves an **INVALID** index behind
  that still costs writes but serves no reads. ``IF NOT EXISTS`` will then
  happily skip it on a re-run, so the guard below explicitly drops any invalid
  leftover first rather than inheriting one silently.
* It waits for every transaction older than itself to finish. A long-running
  reporting query can stall the build without blocking anything else.

Why the indexes are wanted at all: Postgres does not index the referencing side
of a foreign key automatically. Without one, deleting an ``inference_types`` row
forces a sequential scan of both PPU tables to check for references, and the
catalogue joins added in phase 2 lose their index path.

Revision ID: 7e0413f48308
Revises: 11f21f7d7ae4
Create Date: 2026-09-03 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7e0413f48308'
down_revision: Union[str, None] = '11f21f7d7ae4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")

_TABLES = ("tier_quotas", "quota_usage")


def _drop_if_invalid(conn, index_name: str) -> None:
    """Remove a leftover INVALID index from a previously failed CONCURRENTLY run.

    Without this, `CREATE INDEX CONCURRENTLY IF NOT EXISTS` sees the invalid
    index, skips the build, and leaves a permanently useless index that still
    slows every write.
    """
    invalid = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_index i"
            "  JOIN pg_class c ON c.oid = i.indexrelid"
            " WHERE c.relname = :name AND NOT i.indisvalid"
        ),
        {"name": index_name},
    ).first()
    if invalid:
        logger.warning(
            "dropping INVALID index %s left by an earlier failed "
            "CREATE INDEX CONCURRENTLY", index_name,
        )
        conn.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))


def upgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for table in _TABLES:
            index_name = f"ix_{table}_inference_type_id"
            _drop_if_invalid(conn, index_name)
            conn.execute(
                sa.text(
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}"'
                    f'  ON {table} (inference_type_id)'
                )
            )
            logger.info("%s built concurrently", index_name)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for table in _TABLES:
            conn.execute(
                sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "ix_{table}_inference_type_id"')
            )
