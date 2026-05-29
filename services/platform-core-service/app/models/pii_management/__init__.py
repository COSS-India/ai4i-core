"""
SQLAlchemy ORM models for the PII management domain.

These models map to the ai4i_platform database (not the core DB) and therefore
use their own declarative Base — PiiBase — so SQLAlchemy never conflates them
with the core mm_models / mm_services tables.
"""

from sqlalchemy.orm import declarative_base

PiiBase = declarative_base()

from app.models.pii_management.audit_log import AuditLog          # noqa: E402
from app.models.pii_management.domain_policy import DomainPolicy  # noqa: E402
from app.models.pii_management.pattern import PatternLibrary, GeoLibrary  # noqa: E402
from app.models.pii_management.tenant_map import TenantPiiDomainMap  # noqa: E402

__all__ = [
    "PiiBase",
    "AuditLog",
    "DomainPolicy",
    "PatternLibrary",
    "GeoLibrary",
    "TenantPiiDomainMap",
]
