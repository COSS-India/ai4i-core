"""Readable ``audit_logs.message`` for TENANT status changes.

``tenant_status_changed`` takes the audit snapshots (``t.before`` /
``t.after_now()``) and returns a short text built from the templates in
``app.core.messages``: what happened, then the reason.
"""

from __future__ import annotations

from typing import Any, Optional

from app.core import messages as msg
from app.models.tenant import TenantStatus


def _display(value: Any) -> str:
    return msg.AUDIT_EMPTY_VALUE if value is None or value == "" else str(value)


def _tenant_name(*states: Optional[dict]) -> str:
    for state in states:
        if state and state.get("organisation"):
            return str(state["organisation"])
    return msg.AUDIT_EMPTY_VALUE


def _with_reason(message: str, after: dict) -> str:
    reason = after.get("reason")
    if reason is None or str(reason).strip() == "":
        return message
    return message + msg.AUDIT_REASON_SUFFIX.format(reason=reason)


def tenant_status_changed(before: Optional[dict], after: dict) -> str:
    """Suspend / deactivate / activate, or PENDING -> ACTIVE (contact admin
    completed setup), followed by the reason given with the change
    (``after["reason"]``) when there is one. Who made the change and when
    are the row's ``performed_by`` and ``created_at``."""
    name = _tenant_name(after, before)
    old = (before or {}).get("status")
    new = after.get("status")

    if new == TenantStatus.ACTIVE.value and old == TenantStatus.PENDING.value:
        return msg.AUDIT_TENANT_SETUP_COMPLETED.format(name=name)

    if new == TenantStatus.SUSPENDED.value:
        message = msg.AUDIT_TENANT_SUSPENDED.format(name=name)
    elif new == TenantStatus.DEACTIVATED.value:
        message = msg.AUDIT_TENANT_DEACTIVATED.format(name=name)
    elif new == TenantStatus.ACTIVE.value:
        message = msg.AUDIT_TENANT_REACTIVATED.format(name=name)
    else:
        message = msg.AUDIT_TENANT_STATUS_CHANGED.format(
            name=name, old=_display(old), new=_display(new)
        )
    return _with_reason(message, after)
