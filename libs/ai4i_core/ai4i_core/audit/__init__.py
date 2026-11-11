"""Generic audit log: one ``audit_logs`` table in ai4iplatform_core.

See ``writer`` for the write pattern.
"""

from ai4i_core.audit.diff import diff
from ai4i_core.audit.enums import AuditAction, AuditEntity
from ai4i_core.audit.models import AuditBase, AuditLog
from ai4i_core.audit.repository import AuditLogRepository
from ai4i_core.audit.snapshot import (
    BOOKKEEPING_COLUMNS,
    SnapshotRule,
    get_snapshot_rule,
    register_snapshot_rule,
    snapshot,
    to_json_value,
)
from ai4i_core.audit.writer import AuditLogWriter, AuditTracker, noop_audit_writer

__all__ = [
    "AuditAction",
    "AuditBase",
    "AuditEntity",
    "AuditLog",
    "AuditLogRepository",
    "AuditLogWriter",
    "AuditTracker",
    "BOOKKEEPING_COLUMNS",
    "SnapshotRule",
    "diff",
    "get_snapshot_rule",
    "noop_audit_writer",
    "register_snapshot_rule",
    "snapshot",
    "to_json_value",
]
