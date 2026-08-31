"""One-off backfill: allocated_percentage for API Keys created via the
``budget`` (raw ₹ ceiling) create_api_key path before it started deriving
and persisting allocated_percentage alongside allocated_budget.

Those keys have allocated_percentage=NULL and allocated_budget set. Every
allocation cap check (sum_api_key_allocated_percentage, used by both
create_api_key's ALLOCATION_TOTAL_EXCEEDED check and PUT /auth/allocations'
resolve_level) sums allocated_percentage — a NULL there is silently treated
as 0%, so these keys' real share of their Application's budget is invisible
to every cap check that runs after them. An Application can end up pushed
past 100% allocated by keys that, on paper, look like they're contributing
nothing.

This computes allocated_percentage = allocated_budget / application.
allocated_budget * 100, quantized the same way create_api_key itself
quantizes a freshly-converted percentage (0.01, ROUND_HALF_UP) — so a
backfilled key is indistinguishable from one that had gone through the
fixed code path from the start.

Idempotent: only ever touches rows where allocated_percentage IS NULL, so
a second run finds nothing left to do.

Usage:
    python -m scripts.backfill_allocated_percentage_for_budget_keys           # dry run (default)
    python -m scripts.backfill_allocated_percentage_for_budget_keys --apply   # actually writes
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import get_db, init_database
from app.models.api_key import APIKey
from app.models.application import Application

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_allocated_percentage")


def compute_percentage(allocated_budget: Decimal, application_budget: Decimal) -> Decimal:
    """Same formula and quantization create_api_key uses when converting a
    fresh ``budget`` request into allocated_percentage — a backfilled key
    must be indistinguishable from one that went through that path live."""
    return (allocated_budget / application_budget * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


async def _run(*, apply: bool) -> None:
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )

    async for db in get_db():
        rows = (
            await db.execute(
                select(APIKey.id, APIKey.allocated_budget, Application.allocated_budget.label("app_budget"))
                .join(Application, APIKey.application_id == Application.id)
                .where(APIKey.allocated_percentage.is_(None), APIKey.allocated_budget.isnot(None))
            )
        ).all()

        if not rows:
            logger.info("No keys need backfilling — nothing to do.")
            return

        to_update: dict[int, Decimal] = {}
        skipped: list[int] = []
        for row in rows:
            if not row.app_budget:
                # Application has no budget of its own (or lost it since) —
                # a percentage can't be derived; needs a human to look at it.
                skipped.append(row.id)
                continue
            to_update[row.id] = compute_percentage(row.allocated_budget, row.app_budget)

        logger.info("%d key(s) to backfill, %d skipped (no Application budget):", len(to_update), len(skipped))
        for key_id, percentage in to_update.items():
            logger.info("  api_key.id=%s -> allocated_percentage=%s", key_id, percentage)
        if skipped:
            logger.warning("  skipped api_key.id(s) needing manual review: %s", skipped)

        if not apply:
            logger.info("Dry run — no writes made. Re-run with --apply to persist these.")
            return

        for key_id, percentage in to_update.items():
            await db.execute(
                update(APIKey).where(APIKey.id == key_id).values(allocated_percentage=percentage)
            )
        await db.commit()
        logger.info("Backfilled %d key(s).", len(to_update))
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry run).")
    args = parser.parse_args()
    asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    main()
