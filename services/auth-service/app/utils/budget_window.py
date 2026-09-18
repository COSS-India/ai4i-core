"""Shared helpers for comparing tenants.budget_effective_to against "now".

Used by APIKeyService.create_api_key (the create-time gate, reading
tenants.budget_effective_to directly), validation.py's
_cached_budget_window_is_expired (comparing the value cached in the API
key's own payload — see APIKeyService._build_cache_payload), and
tenant_service.py's own _validate_new_effective_from/
_validate_effective_to_after_from (the PATCH/create window-assignment
checks) — kept in one place so none of them ever drift on what a date
means here (UTC calendar day, naive datetimes treated as already being
UTC, None meaning "no window was ever set" rather than "always expired").
"""
from datetime import date, datetime, timezone
from typing import Optional


def as_utc_date(value: datetime) -> date:
    """Calendar date in UTC, not the wall-clock instant — a naive (no
    tzinfo) datetime is treated as already being UTC, matching every
    budget-window field's documented contract ("(UTC)" — see
    TenantBudgetRequest.budget_effective_from/_to), rather than silently
    reinterpreting it as local time."""
    return (value.astimezone(timezone.utc) if value.tzinfo else value).date()


def is_budget_window_expired(budget_effective_to: Optional[datetime]) -> bool:
    """True if ``budget_effective_to``'s calendar day (UTC) has passed —
    inclusive of that day itself. budget_effective_to is the LAST day the
    window is usable, not the instant it starts being unusable: a tenant
    with budget_effective_to = 2026-10-10 (any time of day, since only the
    date component is compared) can still be served all through Oct 10 UTC,
    and only becomes expired once Oct 11 UTC begins.

    None means the tenant never had a window set (including pre-fix rows
    created before this was required) — never expired, not always expired.
    """
    if budget_effective_to is None:
        return False
    return as_utc_date(datetime.now(timezone.utc)) > as_utc_date(budget_effective_to)
