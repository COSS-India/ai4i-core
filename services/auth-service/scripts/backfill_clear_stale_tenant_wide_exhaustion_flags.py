"""One-off remediation: clear budget-exhausted flags the OLD tenant-wide
fan-out (removed by this release) wrote for keys that were never
individually over their own ceiling.

Before this release, one API Key crossing its own budget flipped
budget-exhausted for every sibling Key under the same tenant (the bug
set_budget_exhausted_for_key/set_budget_exhausted_for_keys exists to fix).
Those incorrectly-flagged keys are stuck 429ing at /auth/validate
(app/routes/validation.py) in production right now, and the new code path
only clears a key's flag as a side effect of a reallocation that actually
touches that same key (AllocationService._clear_exhaustion_for_changed_keys)
— a key nobody happens to reallocate stays stuck forever otherwise.

This re-derives the TRUE exhaustion state per flagged key from
platform-core's budget_usage ledger — the same formula the Kafka billing
consumer itself uses (api_key_budget_used >= api_key_budget_snap, see
deduct_balance_and_update_quota) — and clears the flag only for keys that
formula says are NOT actually exhausted. A key that IS genuinely over its
own ceiling is left flagged, untouched. Correction is applied through
APIKeyService.set_budget_exhausted_for_keys — the exact same batched,
tested application code path a reallocation uses — not hand-rolled SQL, so
this can never diverge from what "clearing a key's flag" means anywhere
else in the codebase.

Idempotent: re-running finds fewer (ideally zero) flagged-but-not-really-
exhausted keys each time, since the ones already corrected no longer show
budget-exhausted="1".

Usage:
    python -m scripts.backfill_clear_stale_tenant_wide_exhaustion_flags           # dry run (default)
    python -m scripts.backfill_clear_stale_tenant_wide_exhaustion_flags --apply   # actually writes
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db, get_platform_core_db, init_database, init_platform_core_database
from app.core.redis import get_redis, init_redis
from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from app.services import budget_usage
from app.services.api_key_service import APIKeyService
from app.services.cache_service import CacheService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_clear_stale_exhaustion")


def is_truly_exhausted(used, snap) -> bool:
    """Same formula the Kafka billing consumer itself gates real per-key
    billing on (deduct_balance_and_update_quota's budget_exhausted) — a key
    with no snapshot ceiling, or no usage on record at all, is never
    exhausted; NULL-safe since fetch_budget_usage returns (None, None) for
    a key with no budget_usage row."""
    return snap is not None and used is not None and used >= snap


class UsageLookupFailedError(RuntimeError):
    """Raised when the budget_usage lookup can't be trusted."""


def check_usage_lookup_succeeded(flagged_ids: list, usage_by_key: dict) -> None:
    """fetch_budget_usage is deliberately best-effort: it returns {} on ANY
    platform-core failure, and get_platform_core_db yields None outright
    when PLATFORM_CORE_DB_NAME is unset in the environment this script
    runs from — both are silent from this script's point of view. If they
    happened, every flagged key would classify as (None, None) -> "not
    exhausted" -> cleared, wiping real exhaustion flags on an outage, with
    a dry run that reads identically to a legitimate "nothing is
    exhausted" result.

    A genuinely still-exhausted key always has a budget_usage row (it can
    only have gotten flagged by actually being billed against its own
    ceiling), so an entirely empty result for a non-empty flagged_ids is
    never legitimate — abort rather than guess which case this is."""
    if flagged_ids and not usage_by_key:
        raise UsageLookupFailedError(
            "budget_usage lookup returned nothing for %d flagged key(s) — platform-core may "
            "be unreachable, or PLATFORM_CORE_DB_NAME may be unset in this environment. "
            "Refusing to treat that as 'nothing is exhausted': aborting without writing "
            "anything. Re-run once platform-core is confirmed reachable from here." % len(flagged_ids)
        )


async def _run(*, apply: bool) -> None:
    await init_database(
        db_url=settings.get_database_url(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    await init_redis(
        url=settings.get_redis_url(),
        socket_timeout=settings.redis_timeout,
        redis_db=settings.redis_db,
    )
    init_platform_core_database()

    async for db in get_db():
        async for platform_core_db in get_platform_core_db():
            async for redis in get_redis():
                flagged_ids = (
                    await db.execute(
                        select(APIKey.id).where(
                            APIKey.cached_data["budget-exhausted"].astext == "1",
                            *APIKeyRepository._active_key_conditions(require_cached_data=True),
                        )
                    )
                ).scalars().all()

                if not flagged_ids:
                    logger.info("No keys currently flagged budget-exhausted — nothing to check.")
                    return

                usage_by_key = await budget_usage.fetch_budget_usage(list(flagged_ids), platform_core_db)
                check_usage_lookup_succeeded(list(flagged_ids), usage_by_key)

                to_clear: list[int] = []
                still_exhausted: list[int] = []
                for key_id in flagged_ids:
                    used, snap = usage_by_key.get(key_id, (None, None))
                    (still_exhausted if is_truly_exhausted(used, snap) else to_clear).append(key_id)

                logger.info(
                    "%d key(s) flagged; %d are genuinely over their own ceiling (left alone), "
                    "%d were wrongly flagged by the old tenant-wide fan-out (to clear): %s",
                    len(flagged_ids), len(still_exhausted), len(to_clear), to_clear,
                )

                if not apply:
                    logger.info("Dry run — no writes made. Re-run with --apply to persist these.")
                    return
                if not to_clear:
                    logger.info("Nothing to clear.")
                    return

                api_key_service = APIKeyService(APIKeyRepository(db), CacheService(redis))
                await api_key_service.set_budget_exhausted_for_keys(to_clear, False)
                logger.info("Cleared %d key(s).", len(to_clear))
                return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry run).")
    args = parser.parse_args()
    try:
        asyncio.run(_run(apply=args.apply))
    except UsageLookupFailedError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
