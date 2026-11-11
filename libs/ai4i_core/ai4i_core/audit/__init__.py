"""Generic audit log: one ``audit_logs`` table in ai4iplatform_core.

See ``writer`` for the ``track`` / ``log`` pattern.
"""

from ai4i_core.audit.enums import AuditAction, AuditEntity
from ai4i_core.audit.models import AuditBase, AuditLog
from ai4i_core.audit.repository import AuditLogRepository
from ai4i_core.audit.snapshot import register_audit_entity
from ai4i_core.audit.writer import AuditLogWriter, AuditTrace, noop_audit_writer

__all__ = [
    "AuditAction",
    "AuditBase",
    "AuditEntity",
    "AuditLog",
    "AuditLogRepository",
    "AuditLogWriter",
    "AuditTrace",
    "noop_audit_writer",
    "register_audit_entity",
]
