"""normalise_and_backfill_inference_type_id

Data only. No DDL, no constraint changes, no column drops.

Three things happen here, in order:

  1. ``tier_quotas.inference_name`` is lowercased. Names have been normalised in
     code since phase 1 (``TierQuotaIn.normalize_model_task_type`` does
     ``.strip().lower()``), but rows written before that can still carry mixed
     case. Lowercasing them makes the stored data agree with the normaliser.

     The existing ``uq_tier_quotas_tier_inference`` constraint IS the collision
     check: if one tier holds both 'ASR' and 'asr', the UPDATE raises a unique
     violation. That is deliberate. Those two rows collapse into one under the
     ``(tier_id, inference_type_id)`` constraint added by the next revision, and
     two different monthly_quota values have no correct winner — a human has to
     pick. Failing here, in a data-only migration, is much cheaper than failing
     mid-DDL later.

  2. ``inference_type_id`` is backfilled again on both tables. Revision
     11f21f7d7ae4 already did this, but a type added through POST /inference-types
     since then would have been missed, and its bare ``lower()`` did not rescue
     whitespace-padded legacy rows. ``btrim`` does.

  3. ``tier_quotas`` is hard-gated: any row left without an ``inference_type_id``
     aborts the migration. A tier quota pointing at a type that does not exist is
     a live misconfiguration — the tier looks configured but no billing event can
     ever match it. The table is small enough for a human to adjudicate.

``quota_usage`` is deliberately NOT gated and NOT rewritten. It is append-only
history, and _billing.py documents that ``inference_name=''`` rows occur whenever
mm_services.task_type is unset. Those rows keep a NULL id and their original name
forever; the usage repository left-joins and coalesces so they still appear in
reports. Only their count is reported here.

Because every resolvable name is filled in by step 2, a remaining NULL in
quota_usage means the name is genuinely absent from the catalogue. Such a row has
no resolvable counterpart, so the consumer writing a fresh row beside it records a
different logical type — it is not double counting.

``downgrade()`` is a no-op: the backfill only populated nullable columns and no
reader depends on them being NULL. Lowercasing is not reversed because the
original casing is not recoverable, and nothing reads the column case-sensitively.

Revision ID: 7a35e3b0e8e2
Revises: 11f21f7d7ae4
Create Date: 2026-09-02 00:00:00.000000

"""
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7a35e3b0e8e2'
down_revision: Union[str, None] = '7e0413f48308'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.runtime.migration")

_TABLES = ("tier_quotas", "quota_usage")


def _normalise_tier_quota_names(conn) -> None:
    """Lowercase tier_quotas.inference_name; the unique constraint is the gate."""
    try:
        result = conn.execute(
            sa.text(
                "UPDATE tier_quotas"
                "   SET inference_name = lower(btrim(inference_name))"
                " WHERE inference_name <> lower(btrim(inference_name))"
            )
        )
    except sa.exc.IntegrityError as exc:
        raise RuntimeError(
            "Tier_quotas holds rows that differ only by the case of "
            "inference_name. Lowercasing them collides on "
            "uq_tier_quotas_tier_inference, and they would collide again on the "
            "(tier_id, inference_type_id) constraint added by the next revision. "
            "Merge or delete the duplicates by hand, then re-run. Find them with:\n"
            "  SELECT tier_id, lower(btrim(inference_name)) nm, count(*),"
            " array_agg(inference_name)\n"
            "    FROM tier_quotas GROUP BY 1, 2 HAVING count(*) > 1;"
        ) from exc

    logger.info("Tier_quotas: normalised %s inference_name value(s)", result.rowcount)


def _backfill(conn) -> None:
    """Resolve inference_type_id from inference_name wherever it is still NULL."""
    for table in _TABLES:
        result = conn.execute(
            sa.text(
                f"UPDATE {table} t SET inference_type_id = it.id"
                "   FROM inference_types it"
                "  WHERE t.inference_type_id IS NULL"
                "    AND it.name = lower(btrim(t.inference_name))"
            )
        )
        logger.info("%s: backfilled %s row(s)", table, result.rowcount)


def _gate_tier_quotas(conn) -> None:
    """Abort if any tier grants quota for a type that is not in the catalogue."""
    rows = conn.execute(
        sa.text(
            "SELECT coalesce(nullif(btrim(inference_name), ''), '<empty>') AS nm,"
            "       count(*) AS c"
            "  FROM tier_quotas"
            " WHERE inference_type_id IS NULL"
            " GROUP BY 1 ORDER BY 2 DESC"
        )
    ).all()
    if rows:
        detail = ", ".join(f"{r.nm}={r.c}" for r in rows)
        raise RuntimeError(
            f"Tier_quotas rows with unresolvable inference_name: {detail}. "
            "Each one is a tier granting quota for a type that does not exist, so no "
            "billing event can ever match it. Create the missing type via "
            "POST /inference-types and re-run, or delete the offending rows."
        )


def _report_quota_usage(conn) -> None:
    """Informational only — these rows are expected and stay nullable."""
    rows = conn.execute(
        sa.text(
            "SELECT coalesce(nullif(btrim(inference_name), ''), '<empty>') AS nm,"
            "       count(*) AS c"
            "  FROM quota_usage"
            " WHERE inference_type_id IS NULL"
            " GROUP BY 1 ORDER BY 2 DESC"
        )
    ).all()
    if not rows:
        logger.info("Quota_usage: every row resolved to an inference type")
        return
    detail = ", ".join(f"{r.nm}={r.c}" for r in rows)
    logger.info(
        "Quota_usage: %s unresolvable row(s) left as-is (%s). These keep a NULL "
        "inference_type_id and their original inference_name; usage reports still show "
        "them via the left join.",
        sum(r.c for r in rows),
        detail,
    )


def upgrade() -> None:
    conn = op.get_bind()
    _normalise_tier_quota_names(conn)
    _backfill(conn)
    _gate_tier_quotas(conn)
    _report_quota_usage(conn)


def downgrade() -> None:
    """No-op. Only nullable columns were populated; casing is not recoverable."""
