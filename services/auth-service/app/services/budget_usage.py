"""
Read/write helpers for platform-core's cross-DB ``budget_usage`` ledger —
the ₹-ceiling snapshot and running spend for each API key.

Extracted out of APIKeyService: neither function is API-key *behaviour* —
both are plain, stateless raw-SQL calls against a table APIKeyService
doesn't otherwise own. APIKeyService.create_api_key calls
``write_budget_snapshot`` to seed the ceiling on create; AllocationService
calls both to read consumed amounts and write through resolved ceilings on
edit; GET /auth/api-keys/all calls ``fetch_budget_usage`` directly for its
display values. None of those three has any other reason to import the
other two's classes — importing plain functions from here instead keeps
them decoupled.

There is no ORM relation across the DB boundary — budget_usage.api_key_id
is not a real FK (see migration e9f0a1b2c3d4's comment on
api_key_application_id_fkey) — so both functions are plain raw SQL, not
repository methods on either service's own DB session.
"""

import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def fetch_budget_usage(
    key_ids: list[int],
    platform_core_db: Optional[AsyncSession],
    *,
    raise_on_error: bool = False,
) -> dict[int, tuple[Decimal, Decimal]]:
    """Batch-fetch (used, snapshot) from platform-core's budget_usage ledger.
    Missing entries mean "no usage recorded yet"; callers treat that as used=0.

    Best-effort by default: a platform-core outage must not fail the
    auth-service read it supports (a display value, or a floor-check input
    that already has its own explicit BUDGET_OVERCOMMITTED/
    ALLOCATION_BELOW_CONSUMED handling for the "nothing consumed yet" case)
    — returns {} on any failure rather than raising.

    ``raise_on_error=True`` opts out of that for callers where "query
    succeeded with zero rows" and "query failed" are NOT interchangeable —
    e.g. writing a derived exhaustion flag, where {} on failure would read
    as "zero spend" and overwrite the flag with a wrong value instead of
    leaving it stale. Those callers propagate the exception through their
    own best-effort handling instead.
    """
    if not key_ids or platform_core_db is None:
        return {}
    try:
        rows = (
            await platform_core_db.execute(
                text(
                    "SELECT api_key_id, api_key_budget_used, api_key_budget_snap"
                    "   FROM budget_usage"
                    "  WHERE api_key_id = ANY((:key_ids)::int[])"
                ),
                {"key_ids": key_ids},
            )
        ).all()
    except Exception as exc:
        logger.warning("Failed to fetch budget_usage for keys %s: %s", key_ids, exc)
        if raise_on_error:
            raise
        return {}
    return {
        row.api_key_id: (row.api_key_budget_used, row.api_key_budget_snap) for row in rows
    }


async def write_budget_snapshot(
    snapshots: dict[int, Decimal], platform_core_db: Optional[AsyncSession]
) -> None:
    """Upsert ``budget_usage.api_key_budget_snap`` for every api_key_id in
    ``snapshots`` — the ₹ ceiling each key was actually resolved to.

    Both design docs require this write-through ("the resulting ₹ ceiling
    has to be copied into budget_usage... seeded on create, updated on
    edit") — closed here once, reused by both halves of that requirement:
    ``create_api_key`` (seed) and AllocationService (edit).

    ``api_key_budget_used`` defaults to 0 on insert (matches the column's
    own server_default) and is left alone on conflict — this call only ever
    touches the snapshot ceiling, never the running usage total a different
    writer owns. id is generated here, not left to the DB, since
    ``budget_usage.id`` has no server-side default (Python-side
    ``default=uuid.uuid4`` only, on a model neither caller instantiates
    directly).

    Best-effort, like ``fetch_budget_usage``'s read side: a platform-core
    outage must not block the auth-service allocation write it mirrors —
    the snapshot is a cache of the ceiling, not the ceiling's source of
    truth (``application.allocated_budget`` / ``api_key.allocated_budget``
    in auth-service's own DB are), so a missed write here self-heals the
    next time this same key's allocation changes.
    """
    if not snapshots or platform_core_db is None:
        return
    try:
        for api_key_id, snap in snapshots.items():
            await platform_core_db.execute(
                text(
                    "INSERT INTO budget_usage (id, api_key_id, api_key_budget_snap, api_key_budget_used)"
                    "     VALUES (gen_random_uuid(), :api_key_id, :snap, 0)"
                    "ON CONFLICT (api_key_id)"
                    "   DO UPDATE SET api_key_budget_snap = EXCLUDED.api_key_budget_snap"
                ),
                {"api_key_id": api_key_id, "snap": snap},
            )
        await platform_core_db.commit()
    except Exception as exc:
        logger.warning("Failed to write budget_usage snapshot for keys %s: %s", list(snapshots), exc)
        await platform_core_db.rollback()
