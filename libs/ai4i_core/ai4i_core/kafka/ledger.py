"""Producer-only ledger (ledger_notification_alert, ai4iplatform_core).

One row per (notification, tenant, subject). A BAND row holds current_band +
triggered; a STATE row holds state_hash + triggered. The guarded UPSERT of a
claim is the only authority for "fire": exactly one caller gets a row back.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import text

from . import constants as c
from .constants import Decision
from .keys import subject_json, to_decimal
from .models import NO_LEDGER_ROW, Band, LedgerRef, LedgerState
from .specs import NotificationSpec

# Q-L1 — ledger state, batch read
_READ_MANY_SQL = text(
    """
    SELECT l.notification_id, l.tenant_id, l.subject,
           l.current_band, l.triggered, l.triggered_at
      FROM ledger_notification_alert l
      JOIN unnest(CAST(:notification_ids AS bigint[]),
                  CAST(:tenant_ids       AS varchar[]),
                  CAST(:subjects         AS jsonb[])) AS k(notification_id, tenant_id, subject)
        ON l.notification_id = k.notification_id
       AND l.tenant_id       = k.tenant_id
       AND l.subject         = k.subject
    """
)

# Q-L2 — BAND claim
_CLAIM_BAND_SQL = text(
    """
    INSERT INTO ledger_notification_alert
           (notification_id, tenant_id, subject, current_band,
            triggered, triggered_at, last_event_id)
    VALUES (:notification_id, :tenant_id, CAST(:subject AS JSONB), :band,
            true, now(), :event_id)
    ON CONFLICT (notification_id, tenant_id, subject) DO UPDATE
       SET current_band  = EXCLUDED.current_band,
           triggered     = true,
           triggered_at  = EXCLUDED.triggered_at,
           last_event_id = EXCLUDED.last_event_id,
           updated_at    = now()
     WHERE ledger_notification_alert.triggered = false
        OR EXCLUDED.current_band > ledger_notification_alert.current_band
    RETURNING current_band, triggered, triggered_at
    """
)

# Q-L3 — RESET, monitoring rows only
_RESET_SQL = text(
    """
    UPDATE ledger_notification_alert
       SET triggered  = false,
           updated_at = now()
     WHERE notification_id = :notification_id
       AND tenant_id       = :tenant_id
       AND subject         = CAST(:subject AS JSONB)
       AND triggered       = true
       AND triggered_at   <= now() - make_interval(secs => :cooldown_s)
    RETURNING current_band, triggered, triggered_at
    """
)

# Q-L4 — STATE claim
_CLAIM_STATE_SQL = text(
    """
    INSERT INTO ledger_notification_alert
           (notification_id, tenant_id, subject, state_hash,
            triggered, triggered_at, last_event_id)
    VALUES (:notification_id, :tenant_id, CAST(:subject AS JSONB), :state_hash,
            true, now(), :event_id)
    ON CONFLICT (notification_id, tenant_id, subject) DO UPDATE
       SET state_hash    = EXCLUDED.state_hash,
           triggered     = true,
           triggered_at  = EXCLUDED.triggered_at,
           last_event_id = EXCLUDED.last_event_id,
           updated_at    = now()
     WHERE ledger_notification_alert.state_hash IS DISTINCT FROM EXCLUDED.state_hash
    RETURNING last_event_id
    """
)

# Q-L5 — STATE claim, bulk
_CLAIM_STATE_BULK_SQL = text(
    """
    INSERT INTO ledger_notification_alert
           (notification_id, tenant_id, subject, state_hash,
            triggered, triggered_at, last_event_id)
    SELECT :notification_id, k.tenant_id, k.subject, k.state_hash,
           true, now(), k.event_id
      FROM unnest(CAST(:tenant_ids   AS varchar[]),
                  CAST(:subjects     AS jsonb[]),
                  CAST(:state_hashes AS text[]),
                  CAST(:event_ids    AS uuid[])) AS k(tenant_id, subject, state_hash, event_id)
    ON CONFLICT (notification_id, tenant_id, subject) DO UPDATE
       SET state_hash    = EXCLUDED.state_hash,
           triggered     = true,
           triggered_at  = EXCLUDED.triggered_at,
           last_event_id = EXCLUDED.last_event_id,
           updated_at    = now()
     WHERE ledger_notification_alert.state_hash IS DISTINCT FROM EXCLUDED.state_hash
    RETURNING tenant_id, subject, last_event_id
    """
)

# Q-L6 — re-read one row, after a lost claim
_REREAD_SQL = text(
    """
    SELECT current_band, state_hash, triggered, triggered_at, last_event_id
      FROM ledger_notification_alert
     WHERE notification_id = :notification_id
       AND tenant_id       = :tenant_id
       AND subject         = CAST(:subject AS JSONB)
    """
)

# Q-L8 — quota ledger rows of past months
_PURGE_QUOTA_SQL = text(
    """
    DELETE FROM ledger_notification_alert l
     USING configs_notification_alert c
     WHERE c.id = l.notification_id
       AND c.name IN ('QUOTA_THRESHOLD', 'QUOTA_EXHAUSTED')
       AND l.subject->>'billing_month'
           < to_char(now() - make_interval(months => :months), 'YYYY-MM')
    """
)


def decide(
    spec: NotificationSpec,
    band: Optional[Band],
    state: LedgerState,
    now: datetime,
    cooldown_s: int,
) -> Decision:
    """BAND rule (the decision table of §5.1.1)."""
    open_incident = state.exists and state.triggered
    if band is None:
        if (
            open_incident
            and spec.resets
            and state.triggered_at is not None
            and now - state.triggered_at >= timedelta(seconds=cooldown_s)
        ):
            return Decision.RESET
        return Decision.SKIP
    if not open_incident:
        return Decision.FIRE
    if state.current_band is None or band.value > state.current_band:
        return Decision.FIRE
    return Decision.SKIP


def _state(row) -> LedgerState:
    return LedgerState(
        exists=True,
        current_band=to_decimal(row["current_band"]) if row["current_band"] is not None else None,
        triggered=bool(row["triggered"]),
        triggered_at=row["triggered_at"],
    )


async def read_states(session, refs: Sequence[Tuple[int, LedgerRef]]) -> Dict[str, LedgerState]:
    """Q-L1 for (notification_id, ref) pairs. Refs without a row map to
    NO_LEDGER_ROW (cached as exists: false)."""
    if not refs:
        return {}
    by_identity = {(nid, ref.tenant_id, ref.subject_json): ref for nid, ref in refs}
    states = {ref.key: NO_LEDGER_ROW for _, ref in refs}
    result = await session.execute(
        _READ_MANY_SQL,
        {
            "notification_ids": [nid for nid, _ in refs],
            "tenant_ids": [ref.tenant_id for _, ref in refs],
            "subjects": [ref.subject_json for _, ref in refs],
        },
    )
    for row in result.mappings():
        subject = row["subject"]
        subject_text = subject_json(subject) if isinstance(subject, Mapping) else subject_json(json.loads(subject))
        ref = by_identity.get((int(row["notification_id"]), str(row["tenant_id"]), subject_text))
        if ref is not None:
            states[ref.key] = _state(row)
    return states


async def claim_band(session, notification_id: int, ref: LedgerRef, band_value, event_id: uuid.UUID) -> Optional[LedgerState]:
    """Q-L2. The new state when this caller won the claim, else None."""
    result = await session.execute(
        _CLAIM_BAND_SQL,
        {
            "notification_id": notification_id,
            "tenant_id": ref.tenant_id,
            "subject": ref.subject_json,
            "band": to_decimal(band_value),
            "event_id": event_id,
        },
    )
    row = result.mappings().first()
    return _state(row) if row is not None else None


async def reset_band(session, notification_id: int, ref: LedgerRef, cooldown_s: int) -> Optional[LedgerState]:
    """Q-L3. The re-armed state, or None when the row did not qualify."""
    result = await session.execute(
        _RESET_SQL,
        {
            "notification_id": notification_id,
            "tenant_id": ref.tenant_id,
            "subject": ref.subject_json,
            "cooldown_s": cooldown_s,
        },
    )
    row = result.mappings().first()
    return _state(row) if row is not None else None


async def claim_state(
    session, notification_id: int, tenant_id: str, subject: Mapping[str, str], state_hash: str, event_id: uuid.UUID
) -> bool:
    """Q-L4. True when this caller won the claim."""
    result = await session.execute(
        _CLAIM_STATE_SQL,
        {
            "notification_id": notification_id,
            "tenant_id": str(tenant_id),
            "subject": subject_json(subject),
            "state_hash": state_hash,
            "event_id": event_id,
        },
    )
    return result.first() is not None


@dataclass(frozen=True)
class StateClaim:
    tenant_id: str
    subject: Dict[str, str]
    state_hash: str
    event_id: uuid.UUID


async def claim_state_bulk(session, notification_id: int, claims: Sequence[StateClaim]) -> List[StateClaim]:
    """Q-L5. The claims this call won, in input order."""
    if not claims:
        return []
    result = await session.execute(
        _CLAIM_STATE_BULK_SQL,
        {
            "notification_id": notification_id,
            "tenant_ids": [claim.tenant_id for claim in claims],
            "subjects": [subject_json(claim.subject) for claim in claims],
            "state_hashes": [claim.state_hash for claim in claims],
            "event_ids": [claim.event_id for claim in claims],
        },
    )
    won = {row["last_event_id"] for row in result.mappings()}
    return [claim for claim in claims if claim.event_id in won]


async def reread(session, notification_id: int, ref: LedgerRef) -> LedgerState:
    """Q-L6. The row as it is now (NO_LEDGER_ROW when absent)."""
    result = await session.execute(
        _REREAD_SQL,
        {"notification_id": notification_id, "tenant_id": ref.tenant_id, "subject": ref.subject_json},
    )
    row = result.mappings().first()
    return _state(row) if row is not None else NO_LEDGER_ROW


async def purge_old_quota_rows(session, months: int = c.QUOTA_LEDGER_RETENTION_MONTHS) -> int:
    """Q-L8: delete quota ledger rows of billing months older than `months`."""
    result = await session.execute(_PURGE_QUOTA_SQL, {"months": months})
    return result.rowcount or 0
