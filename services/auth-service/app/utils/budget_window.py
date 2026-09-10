"""Shared helper for comparing tenants.budget_effective_to against "now".

Used by both TenantService.refresh_budget_expiry_flag (the Kafka-billing-
driven Redis flag /auth/validate reads) and APIKeyService.create_api_key
(the create-time gate) — kept in one place so the two never drift on what
"expired" means (UTC calendar instant, naive datetimes treated as already
being UTC, None meaning "no window was ever set" rather than "always
expired").
"""
from datetime import datetime, timezone
from typing import Optional


def is_budget_window_expired(budget_effective_to: Optional[datetime]) -> bool:
    """True if ``budget_effective_to`` has been reached or passed.

    None means the tenant never had a window set (including pre-fix rows
    created before this was required) — never expired, not always expired.
    """
    if budget_effective_to is None:
        return False
    effective_to = budget_effective_to
    if effective_to.tzinfo is None:
        effective_to = effective_to.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= effective_to
