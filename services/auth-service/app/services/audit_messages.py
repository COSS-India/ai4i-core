"""Audit setup for TENANT status changes.

Registers the Tenant model with ai4i_core.audit, names the properties that
are tracked, and picks the message template for a change. The template is
filled (with the acting user and the time) when the audit row is written.
"""

from __future__ import annotations

from typing import Optional

from ai4i_core.audit import AuditEntity, register_audit_entity

from app.core import messages as msg
from app.models.tenant import Tenant, TenantStatus

register_audit_entity(AuditEntity.TENANT, Tenant)

#: Tenant columns read by ``track`` and stored in previous_state / new_state.
TENANT_STATUS_AUDIT_PROPERTIES = ("organisation", "status", "reason")


def tenant_status_template(old_status: Optional[str], new_status: str) -> str:
    """Template for a suspend / deactivate / activate, or PENDING -> ACTIVE
    (contact admin completed setup). The library appends the reason."""
    old = getattr(old_status, "value", old_status)
    new = getattr(new_status, "value", new_status)

    if new == TenantStatus.ACTIVE.value and old == TenantStatus.PENDING.value:
        return msg.AUDIT_TENANT_SETUP_COMPLETED
    if new == TenantStatus.SUSPENDED.value:
        return msg.AUDIT_TENANT_SUSPENDED
    if new == TenantStatus.DEACTIVATED.value:
        return msg.AUDIT_TENANT_DEACTIVATED
    if new == TenantStatus.ACTIVE.value:
        return msg.AUDIT_TENANT_REACTIVATED
    return msg.AUDIT_TENANT_STATUS_CHANGED
