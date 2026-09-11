"""In-memory fast-path cache mirroring ledger_notification_alert.status —
a pre-check in front of the real atomic DB UPSERT in ledger.py, never a
substitute for it.

The DB's guarded UPSERT (INSERT ... ON CONFLICT ... WHERE status IS
DISTINCT FROM EXCLUDED.status) is what stays authoritative under
concurrent/multi-replica writes — that's the actual correctness mechanism
(design doc §5-7). This cache exists only to skip that DB round trip on the
very common case where the status genuinely hasn't changed since this
process last saw it (nothing to record, nothing to publish): a repeated
BUDGET_THRESHOLD check on a tenant sitting at the same percent, or a
BUDGET_EXHAUSTED check on a tenant that's already been marked exhausted.

Being wrong here is always safe, never wrong-in-a-way-that-matters: a
stale or missing cache entry only ever causes one extra DB call (falling
through to the real UPSERT, which still answers correctly) — it can never
cause a missed dedup or a duplicate publish, because the DB WHERE clause is
what actually decides "is this new", not this cache. A cache HIT (status
matches exactly) is what's trusted to skip the DB entirely.

TTL 1 hour, same bound as notification_settings_cache — ledger writes from
ANOTHER process/replica aren't broadcast anywhere (unlike the tiny,
admin-edited configs_notification_alert table, there's no pub/sub channel
for this one; it would be far too chatty, given how often Group B events
can fire), so a stale local view of a row another replica changed
self-heals via this TTL rather than being trusted indefinitely.
"""
import time
from typing import Any, Dict, Tuple

TTL_SECONDS = 3600

_cache: Dict[Tuple[int, str, str, str], Tuple[Dict[str, Any], float]] = {}


def _key(notification_id: int, tenant_id: str, subject_json: str, channel: str) -> Tuple[int, str, str, str]:
    return (notification_id, tenant_id, subject_json, channel)


def matches_cached_status(
    notification_id: int, tenant_id: str, subject_json: str, channel: str, status: Dict[str, Any]
) -> bool:
    """True only when this exact status is already known to be current for
    this row — safe to skip the DB entirely. False for a miss, an expired
    entry, or a different status (all of which fall through to the DB)."""
    entry = _cache.get(_key(notification_id, tenant_id, subject_json, channel))
    if entry is None:
        return False
    cached_status, loaded_at = entry
    if (time.monotonic() - loaded_at) >= TTL_SECONDS:
        return False
    return cached_status == status


def set_cached_status(
    notification_id: int, tenant_id: str, subject_json: str, channel: str, status: Dict[str, Any]
) -> None:
    """Record `status` as the row's now-current value — called after any DB
    check (whether it changed the row or found it already matching), since
    either outcome confirms the DB now holds exactly this status."""
    _cache[_key(notification_id, tenant_id, subject_json, channel)] = (status, time.monotonic())
