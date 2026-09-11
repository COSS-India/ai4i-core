"""
ledger_notification_alert dedup guard — the producer-side "should this
actually be published" decision (design doc §5-7), used AFTER
is_notification_enabled() has already said the notification is turned on.

One evolving row per (notification_id, tenant_id, subject, channel),
updated in place rather than inserted per occurrence — see
infrastructure/databases/migrations/postgres/alembic/versions/
ai4iplatform_core/8f754a278bee_create_ledger_notification_alert_table.py.
notification_id/channels come from the same cached configs_notification_alert
row notification_settings_cache.py already loads (recipient_roles/
threshold_bands live there too).

Every status is the same envelope: {"value": ..., "delivery": "in_progress"
| "sent" | "failed" | "skipped"}. The producer (this module) only ever
writes "value" and sets "delivery" to "in_progress" — a fresh occurrence
that hasn't been delivered yet. Advancing "delivery" to "sent"/"failed"/
"skipped" is the consumer's job once it's actually acted on the row; this
module never reads or writes that transition.

Three "value" shapes, one per event category (design doc §6):
  - THRESHOLD (BUDGET_THRESHOLD/QUOTA_THRESHOLD): the highest percent band
    recorded as reached. A usage reset (a fresh, lower band) differs from
    whatever was stored too, so it fires again without any special-cased
    reset handling.
  - EXHAUSTED (BUDGET_EXHAUSTED/QUOTA_EXHAUSTED): true — an on/off flag,
    fires only on the false/absent -> true transition.
  - Group A admin actions (TIER_ASSIGNED, TIER_CHANGED, BUDGET_ASSIGNED,
    BUDGET_UPDATED, QUOTA_LIMIT_UPDATED): the occurred_at iso timestamp —
    the same one threaded into the Kafka envelope, so two calls that
    resolve to the exact same action (same precomputed timestamp) don't
    double-publish.

All three reduce to one guarded UPSERT: build the candidate `status` JSONB,
INSERT ... ON CONFLICT DO UPDATE ... WHERE status->'value' IS DISTINCT FROM
EXCLUDED.status->'value' RETURNING id. Comparing only the "value" key (not
the whole status object) is what keeps this correct once the consumer
starts changing "delivery" independently — a delivery-only change on the
existing row must never look like "this is a new occurrence" and cause a
duplicate publish; only a genuine value change does. A row coming back
means "this is new, publish"; nothing coming back means "already recorded,
skip". This runs as a real, atomic DB-level guard (not a pure in-memory
decision) so two producer replicas racing the same event can never both
"win" — the in-memory settings cache (notification_id/channels) and the
ledger_cache fast-path below are both pre-checks only, never the source of
truth for dedup.

Before touching the DB at all, ledger_cache.matches_cached_status() is
checked per channel (same "value"-only comparison) — a HIT (this process
already knows the row is at exactly this value) skips the DB entirely for
that channel; a miss/stale/different-value result falls through to the
real UPSERT, which is always correct regardless of what the cache said.
See ledger_cache.py's own docstring for why this can never cause a missed
dedup or a duplicate publish, only an occasional unnecessary DB call.

One row is written per channel configured for the notification — every
channel shares the identical status value in one call, so any channel
transitioning is enough to decide "publish" (all channels are written in the
same transaction regardless, for the consumer's own per-channel delivery
bookkeeping later).
"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from .notification_settings_cache import get_channels, get_notification_id
from .ledger_cache import matches_cached_status, set_cached_status

logger = logging.getLogger(__name__)

_UPSERT_SQL = text(
    """
    INSERT INTO ledger_notification_alert
        (notification_id, tenant_id, subject, channel, status, created_by, updated_by)
    VALUES
        (:notification_id, :tenant_id, CAST(:subject AS JSONB), :channel, CAST(:status AS JSONB), :actor, :actor)
    ON CONFLICT (notification_id, tenant_id, subject, channel)
    DO UPDATE SET
        status = EXCLUDED.status,
        updated_by = EXCLUDED.updated_by,
        updated_at = now()
    WHERE ledger_notification_alert.status->'value' IS DISTINCT FROM EXCLUDED.status->'value'
    RETURNING id
    """
)


async def _record(
    db,
    name: str,
    tenant_id: str,
    subject: Dict[str, Any],
    status: Dict[str, Any],
    actor: str = "",
) -> bool:
    """True if the ledger did not already reflect status["value"] for at
    least one configured channel (i.e. this is new — go ahead and
    publish). False on an unknown/not-yet-cached name (fail closed, same
    reasoning as is_notification_enabled) or when every channel's value
    already matched. `status` must already be the full {"value",
    "delivery"} envelope — built by the three public wrappers below, never
    constructed by a caller directly."""
    notification_id = await get_notification_id(db, name)
    channels: List[str] = await get_channels(db, name)
    if notification_id is None or not channels:
        logger.warning(
            "Ledger check skipped for %s: notification_id/channels not in cache", name
        )
        return False

    subject_json = json.dumps(subject, sort_keys=True)
    status_json = json.dumps(status)

    channels_to_check = [
        channel for channel in channels
        if not matches_cached_status(notification_id, tenant_id, subject_json, channel, status)
    ]
    if not channels_to_check:
        # Every configured channel's cache already reflects this exact
        # status — a confirmed miss, no need to touch the DB at all.
        return False

    fired = False
    try:
        for channel in channels_to_check:
            result = await db.execute(
                _UPSERT_SQL,
                {
                    "notification_id": notification_id,
                    "tenant_id": tenant_id,
                    "subject": subject_json,
                    "channel": channel,
                    "status": status_json,
                    "actor": actor or None,
                },
            )
            if result.first() is not None:
                fired = True
            # Whether the UPSERT changed the row or found it already
            # matching, the DB now holds exactly `status` for this channel.
            set_cached_status(notification_id, tenant_id, subject_json, channel, status)
        await db.commit()
    except Exception as exc:
        logger.warning("Ledger upsert failed for %s/tenant=%s: %s", name, tenant_id, exc)
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    return fired


async def check_and_record_threshold(
    db, name: str, tenant_id: str, subject: Dict[str, Any], percent: int, actor: str = ""
) -> bool:
    return await _record(db, name, tenant_id, subject, {"value": percent, "delivery": "in_progress"}, actor)


async def check_and_record_exhaustion(
    db, name: str, tenant_id: str, subject: Dict[str, Any], actor: str = ""
) -> bool:
    return await _record(db, name, tenant_id, subject, {"value": True, "delivery": "in_progress"}, actor)


async def check_and_record_action(
    db, name: str, tenant_id: str, subject: Dict[str, Any], occurred_at: str, actor: str = ""
) -> bool:
    return await _record(
        db, name, tenant_id, subject, {"value": occurred_at, "delivery": "in_progress"}, actor
    )
