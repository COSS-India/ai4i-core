"""Allowed values for ``audit_logs.entity_name`` and ``audit_logs.action``.

The table stores them as plain VARCHAR; these enums are the only values
``AuditLogWriter`` accepts. Add a member here when a new entity or
action starts being audited — no migration is needed.
"""

from enum import Enum


class AuditEntity(str, Enum):
    TENANT = "TENANT"


class AuditAction(str, Enum):
    STATUS_CHANGE = "STATUS_CHANGE"
