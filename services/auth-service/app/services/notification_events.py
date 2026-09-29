"""auth-service's notification events: TIER_ASSIGNED, TIER_CHANGED,
BUDGET_ASSIGNED and BUDGET_UPDATED, plus the subscription refresh after a
new tenant's subscription rows are seeded.

Each one runs through the shared producer pipeline (ai4i_core.kafka) after
the business change has committed, in the background: a notification
problem never fails or slows the request. Duplicates are stopped by the
state fingerprint in the ledger, so the same change sent twice produces one
event.
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text

from ai4i_core.kafka import (
    NotificationName,
    emit_state,
    format_amount,
    get_notification_runtime,
    notifications_configured,
    refresh_subscriptions,
    run_in_background,
)

logger = logging.getLogger(__name__)

# Tenant budgets are INR-only today; no per-tenant currency column exists yet.
BUDGET_CURRENCY = "INR"

# Q-D1 — name, description and monthly quotas of the old and new tier, in one query
_TIER_DETAILS_SQL = text(
    """
    SELECT t.id::text AS tier_id, t.name, t.description,
           COALESCE(
               json_agg(json_build_object('inference_name', it.name,
                                          'monthly_quota', tq.monthly_quota)
                        ORDER BY it.name) FILTER (WHERE it.id IS NOT NULL),
               '[]'::json) AS quotas
      FROM tiers t
      LEFT JOIN tier_quotas tq     ON tq.tier_id = t.id
      LEFT JOIN inference_types it ON it.id = tq.inference_type_id
     WHERE t.id IN (:new_tier_id, :old_tier_id)
     GROUP BY t.id, t.name, t.description
    """
)


def _quota_lines(quotas) -> List[str]:
    """One "ASR: 1,000 req/mo" line per model task type on the tier."""
    if isinstance(quotas, str):
        quotas = json.loads(quotas)
    return [
        f"{str(q['inference_name']).upper()}: {Decimal(str(q['monthly_quota'])):,.0f} req/mo"
        for q in quotas or []
        if q.get("monthly_quota") is not None
    ]


async def _load_tier_details(new_tier_id: UUID, old_tier_id: Optional[UUID]) -> Dict[str, dict]:
    rt = get_notification_runtime()
    async with rt.core_session_factory() as session:
        result = await session.execute(
            _TIER_DETAILS_SQL, {"new_tier_id": new_tier_id, "old_tier_id": old_tier_id or new_tier_id}
        )
        return {row["tier_id"]: dict(row) for row in result.mappings()}


def publish_tier_event(
    old_tier_id: Optional[UUID],
    new_tier_id: UUID,
    new_tier_name: str,
    tenant_id: int,
    revised_at: Optional[datetime] = None,
) -> None:
    """TIER_ASSIGNED when the tenant had no tier, else TIER_CHANGED.

    ``revised_at`` is the committed tenants.updated_at, for the same reason
    as in publish_budget_event: a tier can be unassigned, so assigned X,
    unassigned, assigned X again repeats {from: None, to: X}, and would be
    dropped as a duplicate without it. A retry of the same commit keeps the
    same value, so it is still deduplicated."""
    if not notifications_configured():
        return
    name = NotificationName.TIER_ASSIGNED if old_tier_id is None else NotificationName.TIER_CHANGED
    new_state = {
        "from_tier_id": str(old_tier_id) if old_tier_id is not None else None,
        "to_tier_id": str(new_tier_id),
        "revised_at": revised_at.isoformat() if revised_at is not None else None,
    }

    async def details() -> list:
        tiers = await _load_tier_details(new_tier_id, old_tier_id)
        new = tiers.get(str(new_tier_id), {})
        description = new.get("description") or ""
        quota_lines = _quota_lines(new.get("quotas"))
        if old_tier_id is None:
            return [new_tier_name, description, quota_lines]
        old_name = tiers.get(str(old_tier_id), {}).get("name") or str(old_tier_id)
        return [old_name, new_tier_name, description, quota_lines]

    fallback = (
        [new_tier_name, "", []] if old_tier_id is None else [str(old_tier_id), new_tier_name, "", []]
    )
    run_in_background(
        emit_state(name, str(tenant_id), new_state, details=details, fallback_details=fallback)
    )


def publish_budget_event(
    tenant_id: int,
    old_budget: Decimal,
    new_budget: Decimal,
    effective_from: Optional[date],
    revised_at: Optional[datetime] = None,
) -> None:
    """BUDGET_ASSIGNED when the budget was 0, else BUDGET_UPDATED.

    ``revised_at`` is the committed tenants.updated_at. It goes into the
    BUDGET_ASSIGNED fingerprint because effective_from is locked once a
    window exists: without it, a tenant topped down to 0 and given the same
    amount again would hash to the stored state and the email would be
    dropped as a duplicate. A retry of the same commit keeps the same value,
    so it is still deduplicated."""
    if not notifications_configured():
        return
    effective = effective_from.isoformat() if effective_from is not None else None
    if old_budget == 0:
        name = NotificationName.BUDGET_ASSIGNED
        new_state = {
            "amount": format_amount(new_budget),
            "effective_from": effective,
            "revised_at": revised_at.isoformat() if revised_at is not None else None,
        }
        details = [BUDGET_CURRENCY, str(new_budget)]
    else:
        name = NotificationName.BUDGET_UPDATED
        new_state = {
            "from_amount": format_amount(old_budget),
            "to_amount": format_amount(new_budget),
            "effective_from": effective,
        }
        details = [BUDGET_CURRENCY, str(old_budget), str(new_budget), effective or date.today().isoformat()]
    run_in_background(emit_state(name, str(tenant_id), new_state, details=details))


def refresh_tenant_subscriptions(tenant_id: int) -> None:
    """After a new tenant's subscription rows commit: SET its K2 value and
    PUBLISH SUBSCRIPTION, so every producer sees the rows at once."""
    if not notifications_configured():
        return
    run_in_background(refresh_subscriptions([str(tenant_id)]))
