"""
SQLAlchemy ORM models for the PII management domain.

These tables live in the primary ai4iplatform_core database alongside the
model-management and alert-management tables. They inherit from the shared
Base (app.models.Base) and use the pii_ prefix to avoid name collisions.
"""

from app.models.pii_management.audit_log import AuditLog
from app.models.pii_management.domain_policy import DomainPolicy
from app.models.pii_management.pattern import GeoLibrary, PatternLibrary
from app.models.pii_management.tenant_map import TenantPiiDomainMap

__all__ = [
    "AuditLog",
    "DomainPolicy",
    "PatternLibrary",
    "GeoLibrary",
    "TenantPiiDomainMap",
]
