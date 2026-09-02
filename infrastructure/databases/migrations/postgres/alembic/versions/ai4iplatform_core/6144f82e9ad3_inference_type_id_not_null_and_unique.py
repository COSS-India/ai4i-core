"""inference_type_id_not_null_and_unique

Additive only. Adds the id-keyed unique constraints **without dropping the
name-keyed ones**, so the currently-deployed consumer — whose ON CONFLICT still
names ``(tenant_id, inference_name, billing_month, tier_id)`` — keeps working
across the migration. That turns what would have been an atomic, stop-the-world
deploy into an ordered and reversible one: apply this, then roll the consumer,
and either half can be rolled back on its own. The old constraints come off in a
later ticket, together with the column.

Keeping both pairs is safe because the two are equivalent from here on: the new
consumer writes ``inference_name`` from the catalogue row it already joined, so
name and id cannot disagree on any row written after it deploys, and the previous
revision proved they agree on every row written before.

``SET NOT NULL`` applies to **tier_quotas only**:

  * tier_quotas needs it. ``UNIQUE (tier_id, inference_type_id)`` is toothless
    against a nullable column, because NULL never equals NULL in a unique index —
    unlimited NULL-id rows could coexist for one tier and the constraint being
    switched *to* would constrain nothing. A NULL row is also a dead quota: the
    consumer's new join cannot match it, so the tier silently grants nothing.
  * quota_usage does not. The consumer inserts ``tq.inference_type_id`` taken from
    the joined tier_quotas row, which is NOT NULL by the bullet above, so it
    structurally cannot write a NULL. Demanding the constraint anyway would force
    every pre-catalogue billing row onto a synthetic sentinel type — real
    complexity and a dashboard relabelling, for a guarantee the join already
    gives. A nullable column is a perfectly legal ON CONFLICT arbiter; inference
    only needs a matching unique index.

Two collision gates, because rows that were distinct under a name key can collide
under an id key:

  * tier_quotas aborts. Two quotas for the same type with different
    monthly_quota have no correct winner. The previous revision normalises casing
    and should already have caught this, so reaching it here means the data moved
    in between.
  * quota_usage merges, after archiving what it removes into
    quota_usage_premerge_2933. Summing consumed units and taking the max snapshot
    is mechanical and lossless, but these are billing rows, so nothing is deleted
    without a copy.

Both merge windows filter ``IS NOT NULL`` on tier_id and inference_type_id: SQL's
PARTITION BY treats NULLs as equal while a unique constraint treats them as
distinct, so without the filters the merge would collapse rows the constraint
would have allowed.

Revision ID: 6144f82e9ad3
Revises: 7a35e3b0e8e2
Create Date: 2026-09-02 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6144f82e9ad3'
down_revision: Union[str, None] = '7a35e3b0e8e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")

_ARCHIVE = "quota_usage_premerge_2933"
_UQ_TIER_QUOTAS = "uq_tier_quotas_tier_inference_type"
_UQ_QUOTA_USAGE = "uq_quota_usage_tenant_type_month_tier"


def _assert_no_null_tier_quota_ids(conn) -> None:
    n = conn.execute(
        sa.text("SELECT count(*) FROM tier_quotas WHERE inference_type_id IS NULL")
    ).scalar()
    if n:
        raise RuntimeError(
            f"AI4IDS-2933: {n} tier_quotas row(s) still have a NULL inference_type_id. "
            "Re-run the previous revision's gate (downgrade -1 then upgrade head) and "
            "resolve whatever it reports before applying this one."
        )


def _gate_tier_quota_collisions(conn) -> None:
    rows = conn.execute(
        sa.text(
            "SELECT tier_id, inference_type_id, count(*) AS c,"
            "       array_agg(DISTINCT inference_name) AS names"
            "  FROM tier_quotas"
            " GROUP BY 1, 2 HAVING count(*) > 1"
        )
    ).all()
    if rows:
        detail = "; ".join(
            f"tier={r.tier_id} type={r.inference_type_id} names={list(r.names)}"
            for r in rows
        )
        raise RuntimeError(
            "AI4IDS-2933: tier_quotas rows would violate "
            f"{_UQ_TIER_QUOTAS}: {detail}. Two quotas for one type on one tier have "
            "no correct winner — merge or delete them by hand, then re-run."
        )


def _merge_quota_usage_collisions(conn) -> None:
    """Sum duplicates into the oldest row, archiving the ones removed."""
    conn.execute(
        sa.text(f"CREATE TABLE IF NOT EXISTS {_ARCHIVE} (LIKE quota_usage INCLUDING DEFAULTS)")
    )

    ranked = (
        "SELECT id, first_value(id) OVER ("
        "         PARTITION BY tenant_id, inference_type_id, billing_month, tier_id"
        "         ORDER BY created_at, id) AS keep_id"
        "  FROM quota_usage"
        " WHERE tier_id IS NOT NULL AND inference_type_id IS NOT NULL"
    )

    archived = conn.execute(
        sa.text(
            f"WITH ranked AS ({ranked})"
            f" INSERT INTO {_ARCHIVE}"
            "  SELECT q.* FROM quota_usage q JOIN ranked r ON r.id = q.id"
            "   WHERE r.id <> r.keep_id"
        )
    ).rowcount
    if not archived:
        logger.info("[2933] quota_usage: no id-keyed collisions to merge")
        return

    conn.execute(
        sa.text(
            f"WITH ranked AS ({ranked}),"
            "      agg AS ("
            "        SELECT r.keep_id,"
            "               sum(q.monthly_quota_used) AS used,"
            "               max(q.monthly_quota_snap) AS snap"
            "          FROM ranked r JOIN quota_usage q ON q.id = r.id"
            "         GROUP BY r.keep_id HAVING count(*) > 1"
            "      )"
            " UPDATE quota_usage q"
            "    SET monthly_quota_used = agg.used,"
            "        monthly_quota_snap = agg.snap,"
            "        updated_at = now()"
            "   FROM agg WHERE q.id = agg.keep_id"
        )
    )
    deleted = conn.execute(
        sa.text(f"DELETE FROM quota_usage q USING {_ARCHIVE} p WHERE q.id = p.id")
    ).rowcount
    logger.info(
        "[2933] quota_usage: merged %s duplicate row(s) into their oldest sibling; "
        "originals archived in %s",
        deleted, _ARCHIVE,
    )


def upgrade() -> None:
    conn = op.get_bind()

    _assert_no_null_tier_quota_ids(conn)
    _gate_tier_quota_collisions(conn)
    _merge_quota_usage_collisions(conn)

    # tier_quotas only — see the module docstring for why quota_usage is excluded.
    op.alter_column(
        "tier_quotas", "inference_type_id", existing_type=sa.Integer(), nullable=False
    )

    op.create_unique_constraint(
        _UQ_TIER_QUOTAS, "tier_quotas", ["tier_id", "inference_type_id"]
    )
    op.create_unique_constraint(
        _UQ_QUOTA_USAGE,
        "quota_usage",
        ["tenant_id", "inference_type_id", "billing_month", "tier_id"],
    )


def downgrade() -> None:
    """Reverses the DDL. The merge is NOT reversed automatically.

    quota_usage_premerge_2933 still holds every row the merge deleted, but the
    surviving rows keep their summed totals — re-deriving them is a manual,
    case-by-case job. Take a pg_dump before upgrading; the archive is a
    convenience, not a substitute.

    Never run this while the new consumer is live: its ON CONFLICT names the
    constraint being dropped here, so every billing message would fail. Roll the
    consumer back first, then the schema.
    """
    op.drop_constraint(_UQ_QUOTA_USAGE, "quota_usage", type_="unique")
    op.drop_constraint(_UQ_TIER_QUOTAS, "tier_quotas", type_="unique")
    op.alter_column(
        "tier_quotas", "inference_type_id", existing_type=sa.Integer(), nullable=True
    )
