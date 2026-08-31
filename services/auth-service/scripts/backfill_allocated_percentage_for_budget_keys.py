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

Writing these NULLs in is exactly what can newly reveal (not cause) an
Application already over-allocated — its keys' real shares were invisible
to every cap check until now. This reports, per Application, the ones that
land over 100% once the backfill is applied — a human has to decide how to
resolve each one (nothing here revokes or shrinks a Key's own allocation);
otherwise that Application stays invisibly over-allocated until the next
unrelated create_api_key call for it fails with ALLOCATION_TOTAL_EXCEEDED
for a confused caller.

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
from app.repositories.application_repository import ApplicationRepository

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_allocated_percentage")


def compute_percentage(allocated_budget: Decimal, application_budget: Decimal) -> Decimal:
    """Same formula and quantization create_api_key uses when converting a
    fresh ``budget`` request into allocated_percentage — a backfilled key
    must be indistinguishable from one that went through that path live."""
    return (allocated_budget / application_budget * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sum_new_percentages_by_application(
    application_id_by_key: dict[int, int], percentage_by_key: dict[int, Decimal]
) -> dict[int, Decimal]:
    """Sum just the percentages this backfill is about to ADD, grouped by
    the Application they land under — the piece existing_total_by_application
    (already-persisted, unaffected keys) doesn't include."""
    totals: dict[int, Decimal] = {}
    for key_id, percentage in percentage_by_key.items():
        app_id = application_id_by_key[key_id]
        totals[app_id] = totals.get(app_id, Decimal("0")) + percentage
    return totals


def applications_over_100(
    new_total_by_application: dict[int, Decimal], existing_total_by_application: dict[int, Decimal]
) -> dict[int, Decimal]:
    """{application_id: final_total} for every Application whose EXISTING
    allocated_percentage total (already-persisted, non-NULL keys — what
    sum_api_key_allocated_percentage reads today, before this backfill
    writes anything) plus the percentages this backfill is about to add
    exceeds 100 — the exact condition ALLOCATION_TOTAL_EXCEEDED enforces on
    every live create_api_key/PUT /auth/allocations call, made visible here
    instead of surfacing later as a confusing failure on an unrelated
    request."""
    over: dict[int, Decimal] = {}
    for app_id, new_total in new_total_by_application.items():
        final_total = existing_total_by_application.get(app_id, Decimal("0")) + new_total
        if final_total > Decimal("100"):
            over[app_id] = final_total
    return over


async def _run(*, apply: bool) -> None:
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )

    async for db in get_db():
        rows = (
            await db.execute(
                select(
                    APIKey.id,
                    APIKey.application_id,
                    APIKey.allocated_budget,
                    Application.allocated_budget.label("app_budget"),
                )
                .join(Application, APIKey.application_id == Application.id)
                .where(APIKey.allocated_percentage.is_(None), APIKey.allocated_budget.isnot(None))
            )
        ).all()

        if not rows:
            logger.info("No keys need backfilling — nothing to do.")
            return

        to_update: dict[int, Decimal] = {}
        application_id_by_key: dict[int, int] = {}
        skipped: list[int] = []
        for row in rows:
            if not row.app_budget:
                # Application has no budget of its own (or lost it since) —
                # a percentage can't be derived; needs a human to look at it.
                skipped.append(row.id)
                continue
            to_update[row.id] = compute_percentage(row.allocated_budget, row.app_budget)
            application_id_by_key[row.id] = row.application_id

        logger.info("%d key(s) to backfill, %d skipped (no Application budget):", len(to_update), len(skipped))
        for key_id, percentage in to_update.items():
            logger.info("  api_key.id=%s -> allocated_percentage=%s", key_id, percentage)
        if skipped:
            logger.warning("  skipped api_key.id(s) needing manual review: %s", skipped)

        new_total_by_application = sum_new_percentages_by_application(application_id_by_key, to_update)
        applications = ApplicationRepository(db)
        existing_total_by_application = {
            app_id: await applications.sum_api_key_allocated_percentage(app_id)
            for app_id in new_total_by_application
        }
        over_100 = applications_over_100(new_total_by_application, existing_total_by_application)
        if over_100:
            logger.warning(
                "%d Application(s) will be over 100%% allocated once this backfill lands — "
                "these need a human decision, nothing here shrinks a Key's own allocation:",
                len(over_100),
            )
            for app_id, final_total in over_100.items():
                logger.warning("  application.id=%s -> total allocated_percentage=%s", app_id, final_total)
        else:
            logger.info("No Application ends up over 100%% allocated after this backfill.")

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
